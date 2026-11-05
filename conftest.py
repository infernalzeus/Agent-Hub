"""pytest: never collect the hub's own data folder (mission working copies there are whole copies of the repo, tests included)."""
collect_ignore_glob = ["data/*"]
