"Publication pages."

from __future__ import print_function

import logging

import tornado.web

from . import constants
from . import crossref
from . import pubmed
from . import settings
from . import utils
from .saver import Saver, SaverError
from .requesthandler import RequestHandler


FETCH_ERROR = 'Could not fetch article for some reason.'
TRASHED_MSG = 'Article was trashed at some earlier time.'

class PublicationSaver(Saver):
    doctype = constants.PUBLICATION


class PublicationMixin(object):
    "Mixin of access check methods."

    def is_editable(self, publication):
        "Is the publication editable by the current user?"
        return self.is_curator()

    def check_editable(self, publication):
        "Check that the publication is editable by the current user."
        if self.is_editable(publication): return
        raise ValueError('You many not edit the publication.')

    def is_trashable(self, publication):
        "Is the publication trashable by the current user?"
        return self.is_curator()

    def check_trashable(self, publication):
        "Check that the publication is trashable by the current user."
        if self.is_trashable(publication): return
        raise ValueError('You may not trash the publication.')


class Publication(PublicationMixin, RequestHandler):
    "Display the publication."

    def get(self, identifier):
        "Display the publication."
        try:
            publication = self.get_publication(identifier)
        except KeyError:
            raise tornado.web.HTTPError(404, reason='No such publication.')
        self.render('publication.html',
                    publication=publication,
                    is_editable=self.is_editable(publication))


class Publications(RequestHandler):
    "Publications page."

    TEMPLATE = 'publications.html'

    def get(self, year=None):
        if year:
            publications = self.get_docs('publication/year',
                                         key=year,
                                         reduce=False)
            publications.sort(key=lambda i: i['published'], reverse=True)
        else:
            publications = self.get_docs('publication/published',
                                         key=constants.CEILING,
                                         last='',
                                         descending=True)
        self.render(self.TEMPLATE,
                    publications=publications,
                    year=year)


class PublicationsTable(Publications):
    "Publications table page."

    TEMPLATE = 'publications_table.html'


class PublicationsUnverified(RequestHandler):
    """Unverified publications page.
    List according to which labels the account may use.
    """

    @tornado.web.authenticated
    def get(self):
        if self.is_admin():
            publications = self.get_docs('publication/unverified',
                                         key=constants.CEILING,
                                         last='',
                                         limit=settings['SHORTLIST_LIMIT'],
                                         descending=True)
        else:
            lookup = {}
            for label in self.current_account.get('labels'):
                docs = self.get_docs('publication/label_unverified',
                                     key=label)
                for doc in docs:
                    lookup[doc['_id']] = doc
            publications = lookup.values()
            publications.sort(key=lambda i: i['published'], reverse=True)
            # XXX All unverified are returned.
        self.render('publications_unverified.html', publications=publications)


class PublicationFetch(RequestHandler):
    "Fetch a publication given its DOI or PMID."

    @tornado.web.authenticated
    def get(self):
        self.check_curator()
        docs = self.get_docs('publication/modified',
                             key=constants.CEILING,
                             last='',
                             descending=True,
                             limit=settings['SHORTLIST_LIMIT'])
        self.render('publication_fetch.html',
                    publications=docs,
                    identifier=self.get_argument('identifier', ''))

    @tornado.web.authenticated
    def post(self):
        self.check_curator()
        try:
            identifier = self.get_argument('identifier')
            if not identifier: raise ValueError
        except (tornado.web.MissingArgumentError, ValueError):
            self.see_other('publication_fetch')
            return
        # Check if identifier is present in trash registry
        force = utils.to_bool(self.get_argument('force', False))
        trashed = self.get_trashed(identifier)
        if trashed:
            if force:
                del self.db[trashed]
            else:
                self.see_other('publication_fetch',
                               identifier=identifier,
                               message=TRASHED_MSG)
                return
        # Has it already been fetched?
        try:
            old = self.get_publication(identifier, unverified=True)
        except KeyError:
            old = None
        if constants.PMID_RX.match(identifier):
            try:
                new = pubmed.fetch(identifier)
            except (IOError, requests.exceptions.Timeout):
                self.see_other('publication_fetch', error=FETCH_ERROR)
            else:
                if old is None:
                    try:
                        old = self.get_publication(new.get('doi'))
                    except KeyError:
                        pass
        else:
            try:
                new = crossref.fetch(identifier)
            except (IOError, requests.exceptions.Timeout):
                self.see_other('publication_fetch', error=FETCH_ERROR)
            else:
                if old is None:
                    try:
                        old = self.get_publication(new.get('pmid'))
                    except KeyError:
                        pass
        # Check trash registry again; the other external identifier may be there
        for id in [new.get('pmid'), new.get('doi')]:
            if not id: continue
            trashed = self.get_trashed(id)
            if trashed:
                if force:
                    del self.db[trashed]
                else:
                    self.see_other('publication_fetch',
                                   identifier=identifier,
                                   message=TRASHED_MSG)
                    return
        if old:
            with PublicationSaver(old, rqh=self) as saver:
                for key in new:
                    saver[key] = new[key]
                saver['verified'] = True
            publication = old
        else:
            with PublicationSaver(new, rqh=self) as saver:
                if self.current_user['role'] == constants.CURATOR:
                    saver['labels'] = sorted(self.current_user['labels'])
                else:
                    saver['labels'] = []
                saver['verified'] = True
            publication = new
        self.see_other('publication', publication['_id'])


class PublicationEdit(PublicationMixin, RequestHandler):
    "Edit the publication."

    @tornado.web.authenticated
    def get(self, iuid):
        try:
            publication = self.get_publication(iuid)
        except KeyError:
            raise tornado.web.HTTPError(404, reason='No such publication.')
        self.check_editable(publication)
        if self.is_admin():
            labels = [l['value'] for l in self.get_docs('label/value')]
        else:
            labels = self.current_user['labels']
        self.render('publication_edit.html',
                    title='Edit publication',
                    publication=publication,
                    labels=labels)

    @tornado.web.authenticated
    def post(self, iuid):
        try:
            publication = self.get_publication(iuid)
        except KeyError:
            raise tornado.web.HTTPError(404, reason='No such publication.')
        self.check_editable(publication)
        if self.is_admin():
            allowed_labels = set([l['value'] for l in
                                  self.get_docs('label/value')])
        else:
            allowed_labels = set(self.current_user['labels'])
        try:
            with PublicationSaver(doc=publication, rqh=self) as saver:
                saver.check_revision()
                saver['title'] = self.get_argument('title', '') or '[no title]'
                authors = []
                for author in self.get_argument('authors', '').split('\n'):
                    author = author.strip()
                    if not author: continue
                    try:
                        family, given = author.split(',', 1)
                        family = family.strip()
                        if not family: raise IndexError
                        given = given.strip()
                    except IndexError:
                        family = author
                        given = ''
                    else:
                        initials = ''.join([c[0] for c in given.split()])
                        authors.append(
                            dict(family=family,
                                 family_normalized=utils.to_ascii(family),
                                 given=given,
                                 given_normalized=utils.to_ascii(given),
                                 initials=initials,
                                 initials_normalized=utils.to_ascii(initials)))
                saver['authors'] = authors
                saver['pmid'] = self.get_argument('pmid', '') or None
                saver['doi'] = self.get_argument('doi', '') or None
                journal = dict(title=self.get_argument('journal', '') or None)
                for key in ['issn', 'volume', 'issue', 'pages']:
                    journal[key] = self.get_argument(key, '') or None
                saver['journal'] = journal
                saver['abstract'] = self.get_argument('abstract', '') or None
                saver['labels'] = sorted(l for l in self.get_arguments('labels')
                                         if l in allowed_labels)
                # Edit should not do verify! It must be possible for admin
                # change labels in order to challenge the relevant
                # curators to verify or trash.
        except SaverError, msg:
            self.see_other('publication', publication['_id'],
                           error=utils.REV_ERROR)
        else:
            self.see_other('publication', publication['_id'])


class PublicationVerify(PublicationMixin, RequestHandler):
    "Verify publication."

    @tornado.web.authenticated
    def post(self, identifier):
        try:
            publication = self.get_publication(identifier)
        except KeyError:
            raise tornado.web.HTTPError(404, reason='No such publication.')
        with PublicationSaver(publication, rqh=self) as saver:
            saver['verified'] = True
        try:
            self.redirect(self.get_argument('next'))
        except tornado.web.MissingArgumentError:
            self.see_other('publication', publication['_id'])


class PublicationTrash(PublicationMixin, RequestHandler):
    "Trash a publication and record its external identifiers."

    @tornado.web.authenticated
    def post(self, identifier):
        try:
            publication = self.get_publication(identifier)
        except KeyError:
            raise tornado.web.HTTPError(404, reason='No such publication.')
        self.check_trashable(publication)
        # Delete log entries
        for log in self.get_logs(publication['_id']):
            self.db.delete(log)
        trash = {constants.DOCTYPE: constants.TRASH,
                 'title': publication['title'],
                 'pmid': publication.get('pmid'),
                 'doi': publication.get('doi'),
                 'created': utils.timestamp(),
                 'owner': self.current_user['email']}
        self.db[utils.get_iuid()] = trash
        self.db.delete(publication)
        try:
            self.redirect(self.get_argument('next'))
        except tornado.web.MissingArgumentError:
            self.see_other('home')


class PublicationLabels(PublicationMixin, RequestHandler):
    "Edit labels for publication."

    @tornado.web.authenticated
    def get(self, iuid):
        try:
            publication = self.get_publication(iuid)
        except KeyError:
            raise tornado.web.HTTPError(404, reason='No such publication.')
        self.check_editable(publication)
        if self.is_admin():
            labels = [l['value'] for l in self.get_docs('label/value')]
        else:
            labels = self.current_account['labels']
        self.render('publication_labels.html',
                    title='Edit publication labels',
                    publication=publication,
                    labels=labels)

    @tornado.web.authenticated
    def post(self, iuid):
        try:
            publication = self.get_publication(iuid)
        except KeyError:
            raise tornado.web.HTTPError(404, reason='No such publication.')
        self.check_editable(publication)
        with PublicationSaver(doc=publication, rqh=self) as saver:
            saver['title'] = self.get_argument('title', '') or '[no title]'
            authors = []
            for author in self.get_argument('authors', '').split('\n'):
                author = author.strip()
                if not author: continue
                try:
                    family, given = author.split(',', 1)
                    family = family.strip()
                    if not family: raise IndexError
                    given = given.strip()
                except IndexError:
                    family = author
                    given = ''
                else:
                    initials = ''.join([c[0] for c in given.split()])
                    authors.append(
                        dict(family=family,
                             family_normalized=utils.to_ascii(family),
                             given=given,
                             given_normalized=utils.to_ascii(given),
                             initials=initials,
                             initials_normalized=utils.to_ascii(initials)))
            saver['authors'] = authors
            saver['pmid'] = self.get_argument('pmid', '') or None
            saver['doi'] = self.get_argument('doi', '') or None
            journal = dict(title=self.get_argument('journal', '') or None)
            for key in ['issn', 'volume', 'issue', 'pages']:
                journal[key] = self.get_argument(key, '') or None
            saver['journal'] = journal
            saver['abstract'] = self.get_argument('abstract', '') or None
        self.see_other('publication', publication['_id'])
