"Journal pages."

from __future__ import print_function

import logging

import tornado.web

from . import constants
from . import settings
from . import utils
from .saver import Saver, SaverError
from .requesthandler import RequestHandler
from .publication import PublicationSaver


class JournalSaver(Saver):
    doctype = constants.JOURNAL


class JournalMixin(object):
    "Mixin for access check methods."

    def get_journal(self, title):
        "Get the journal given title or ISSN."
        try:
            return self.get_doc(title, 'journal/title')
        except KeyError:
            try:
                return self.get_doc(title, 'journal/issn')
            except KeyError:
                raise tornado.web.HTTPError(404, reason='No such journal.')

    def is_editable(self, journal):
        return self.is_admin()

    def check_editable(self, journal):
        if self.is_editable(journal): return
        raise ValueError('You may not edit the journal.')

    def is_deletable(self, journal):
        if not self.is_admin(): return False
        if self.get_docs('publication/journal', key=journal['title']):
            return False
        return True

    def check_deletable(self, journal):
        if self.is_deletable(journal): return
        raise ValueError('You may not delete the journal.')


class Journal(JournalMixin, RequestHandler):
    "Journal page with list of articles."

    def get(self, title):
        try:
            journal = self.get_doc(title, 'journal/title')
        except KeyError:
            try:
                journal = self.get_doc(title, 'journal/issn')
            except KeyError:
                raise tornado.web.HTTPError(404, reason='No such journal.')
            else:
                duplicates = self.get_docs('journal/title', key=title)
        else:
            duplicates = self.get_docs('journal/issn', key=journal['issn'])
        duplicates = [d for d in duplicates if d['_id'] != journal['_id']]
        publications = {}
        if journal['title']:
            view = self.db.view('publication/journal', reduce=False)
            for row in view[journal['title']]:
                try:
                    publications[row.id] += 1
                except KeyError:
                    publications[row.id] = 1
        if journal['issn']:
            view = self.db.view('publication/issn', reduce=False)
            for row in view[journal['issn']]:
                try:
                    publications[row.id] += 1
                except KeyError:
                    publications[row.id] = 1
        publications = [self.db[i] for i in publications]
        publications.sort(key=lambda p: p['published'], reverse=True)
        self.render('journal.html',
                    journal=journal,
                    is_editable=self.is_editable(journal),
                    is_deletable=self.is_deletable(journal),
                    publications=publications,
                    duplicates=duplicates)

    @tornado.web.authenticated
    def post(self, title):
        if self.get_argument('_http_method', None) == 'delete':
            self.delete(title)
            return
        raise tornado.web.HTTPError(
            405, reason='Internal problem; POST only allowed for DELETE.')

    @tornado.web.authenticated
    def delete(self, title):
        try:
            journal = self.get_doc(title, 'journal/title')
        except KeyError:
            raise tornado.web.HTTPError(404, reason='No such journal.')
        self.check_deletable(journal)
        self.delete_entity(journal)
        self.see_other('journals')


class JournalEdit(JournalMixin, RequestHandler):
    "Edit the journal title or ISSN. Modifies affected publications."

    @tornado.web.authenticated
    def get(self, title):
        journal = self.get_journal(title)
        self.check_editable(journal)
        self.render('journal_edit.html',
                    is_editable=self.is_editable(journal),
                    is_deletable=self.is_deletable(journal),
                    journal=journal)

    @tornado.web.authenticated
    def post(self, title):
        journal = self.get_journal(title)
        self.check_editable(journal)
        old_title = journal['title']
        old_issn = journal.get('issn')
        with JournalSaver(doc=journal, rqh=self) as saver:
            saver.check_revision()
            try:
                title = self.get_argument('title')
            except tornado.web.MissingArgumentError:
                self.see_other('journal', error='No title provided.')
                return
            saver['title'] = title
            saver['issn'] = issn = self.get_argument('issn', None) or None
        if old_title != title or old_issn != issn:
            view = self.db.view('publication/journal',
                                key=old_title,
                                include_docs=True,
                                reduce=False)
            for row in view:
                with PublicationSaver(doc=row.doc, rqh=self) as saver:
                    journal  = saver['journal'].copy()
                    journal['title'] = title
                    journal['issn'] = issn
                    saver['journal'] = journal
        self.see_other('journal', journal['title'])

    
class Journals(RequestHandler):
    "Journals table page."

    def get(self):
        journals = self.get_docs('journal/title')
        view = self.db.view('publication/journal', group=True)
        counts = dict([(r.key, r.value) for r in view])
        for journal in journals:
            journal['count'] = counts.get(journal['title'], 0)
        self.render('journals.html', journals=journals)