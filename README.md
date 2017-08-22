Publications
============

A simple web-based publications reference database system.

See the [wiki](wiki) for the documentation, including How-to and
Installation.

Features
--------

- Publication references can be added by fetching data from:

  - [PubMed](https://www.ncbi.nlm.nih.gov/pubmed)
    using the PubMed identifier (PMID).
  - [Crossref](https://www.crossref.org/)
     using the Digital Object Identifier (DOI).

- Publication references can be added manually.

- Curator accounts for adding and editing the publication entries can
  be created by the admin of the instance.

- All curators can edit every publication reference. There is a log
  for each publication, so it is possible to see who did what when.

- Publication references can be labeled. The labels can be used to
  indicate e.g. research group, facility or some other classification.

- A curator can use only the labels that she has been assigned by the
  admin.

- Publication references can be set as unverified when loading them by
  automated scripts. A curator must then verify each such publication
  manually.

- There is a blacklist registry based on the PMID and/or DOI of
  publications.  When a publication is blacklisted, it will not be
  fetched when using PMID, DOI or automatic scripts. This is to avoid
  adding publications that have already been determined to be
  irrelevant.

- The publications data can be extracted in JSON and CSV formats. The
  CSV format allows some basic filtering options.


Implementation
--------------

Front-end: Bootstrap 3, jQuery, jQuery UI, DataTables

Back-end: Python 2.7, tornado, CouchDB, pyyaml, requests


SciLifeLab
----------

The system was designed for keeping track of the publications
to which the facilities of SciLifeLab contributed.
See [SciLifeLab Publications](https://publications.scilifelab.se/).

The data is available at [README](publications/scilifelab/README.md).
