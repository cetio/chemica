"""Source implementations — one module per data source.

First increment ships `pubchem` and `wikipedia`. The Source protocol in
`chemica.core` is the contract; each module exposes a class implementing it.
"""

from chemica.sources.pubchem import PubChemSource
from chemica.sources.wikipedia import WikipediaSource

__all__ = ["PubChemSource", "WikipediaSource"]
