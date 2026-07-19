"""File-first configuration adapters (spec D22/D23).

Loads the versioned workspace config file (YAML/JSON) into
:class:`bizkit.config.BizkitConfig` plus table configs and grants, and
provides the default ``TableRegistry`` and ``AccessPolicy`` adapters over
that data.
"""

from bizkit.workspace.access import FileAccessPolicy
from bizkit.workspace.loader import LoadedWorkspace, WorkspaceFile, load_workspace
from bizkit.workspace.registry import FileTableRegistry

__all__ = [
    "FileAccessPolicy",
    "FileTableRegistry",
    "LoadedWorkspace",
    "WorkspaceFile",
    "load_workspace",
]
