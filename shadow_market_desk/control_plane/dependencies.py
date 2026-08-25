from .repositories import RepositoryBundle, build_default_repositories

_REPOSITORIES = build_default_repositories()


def get_repositories() -> RepositoryBundle:
    return _REPOSITORIES
