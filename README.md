# Chemica

> [!NOTE]
> Future development for Chemica is currently ambiguous. It will likely remain a floating repository for various API integrations and data sources for the foreseeable future.

Chemica is a PubChem wiki app for compounds with integration for Wikipedia, Psychonaut Wiki, PubMed, and PMC. Searches are automatically sources from PubMed, with 3D molecular viewing, chemical properties, identifiers, and more.


https://github.com/user-attachments/assets/33b72559-45b5-4a8c-ad70-571d5741e524


## Features

Chemica aims to have a diverse knowledge-set available, sourcing from Wikipedia, Psychonaut Wiki, PubMed, and PMC with support for local AI synthesis to blend information from multiple sources.

Among Chemica's features are:

- **3D molecular view** (small and expanded) with atomic tooltips and full bond visualization.
- **Chemical properties** (XLogP, MW, formula, charge, energy, etc.)
- **Chemical identifiers** (SMILES, InChI, InChIKey, CAS, etc.)
- **Automatic aggregation of dosage information** ROA, bioavailability, and thresholds.
- **Similarity matching** structural scoring, XLogP, and MW to locate compounds with similar dosage to fill gaps.

### Integrated Knowledge Sources
- **Wikipedia** - Search, article retrieval, and structured data extraction (PubChem CIDs)
- **PsychonautWiki** - Specialized wiki access for substance information and Erowid cross-references
- **PubMed** - Biomedical literature database integration via NCBI Entrez
- **PMC** - PubMed Central full-text articles and research papers

## Architecture

- `akashi.pubchem` - PubChem API integration.
- `akashi.wikipedia` - Wikipedia API interaction and parser.
- `akashi.psychonaut` - PsychonautWiki and Erowid data integration.
- `akashi.entrez` - NCBI research database access (PubMed, PMC).
- `akashi.text` - Wikitext and XML parsing utilities.
- `infer.ease` - AI inference for easing multiple sources.
- `infer.config` - Configuration for AI inference.
- `infer.resolve` - Exclusion and suffix based resolution for compounds.
- `gui` - GUI for Chemica using GTK.

## License

Chemica is licensed under the [AGPL-3.0 license](LICENSE.txt).
