library(tidyverse)
library(kyber)
library(jupycost)
library(gh)
library(yaml)

# Get the teams that provide access to the NMFS hub
prod_teams_hub_access <- read_yaml(
  "https://raw.githubusercontent.com/2i2c-org/infrastructure/refs/heads/main/config/clusters/nmfs-openscapes/prod.values.yaml"
) |>
  pluck(
    "jupyterhub",
    "hub",
    "config",
    "GitHubOAuthenticator",
    "allowed_organizations"
  ) |>
  str_remove("^nmfs-openscapes:") |>
  tolower()

# Get all NMFS teams and add users
nmfs_teams <- list_teams("nmfs-openscapes", names_only = FALSE) |>
  rename(team = slug) |>
  mutate(
    name = map(team, \(x) tolower(list_team_members(x, "nmfs-openscapes")))
  ) |>
  # join access teams so that we know if/how they are getting access to the hub
  left_join(
    data.frame(team = prod_teams_hub_access, hub_access = TRUE),
    by = "team"
  ) |>
  mutate(hub_access = replace_na(hub_access, FALSE)) |>
  select(team, hub_access, name)

# Unnest so one row per user per team
nmfs_teams_members <- unnest(nmfs_teams, cols = name)

# Get directory usage stats from Grafana
dir_size_usage <- user_dir_snapshot(
  "https://grafana.nmfs-openscapes.2i2c.cloud",
  grafana_token = Sys.getenv("NMFS_GRAFANA_TOKEN")
) |>
  filter(namespace == "prod") |>
  mutate(name = tolower(directory), .keep = "unused")

# Join member/team info to home dir info
teams_members_dir_info <- nmfs_teams_members |>
  left_join(
    dir_size_usage |>
      select(name, last_accessed, dirsize_mb),
    by = "name"
  )

# Collapse so one row per user, teams in a comma-separated list
members_team_info <- nmfs_teams_members |>
  group_by(name) |>
  summarise(
    n_teams = length(team),
    teams = paste(team, collapse = ";"),
    hub_access = any(hub_access)
  ) |>
  left_join(
    dir_size_usage |>
      select(name, last_accessed, dirsize_mb),
    by = "name"
  )

write_csv(members_team_info, "nmfs-gh-team-members-access_2026-01-20.csv")
