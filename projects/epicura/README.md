# Epicura

Epicura's project map and playbooks live with the project, under `Agents/` in its private PM repo (`manasXP/epicura-pm`), so they change with it. On the author's machine that is `__Workspaces/Appliance/Epicura/epi-PM/Agents/project-map.yaml` in the vault, targeting `~/code/Epicura`.

`validate.py` with no arguments checks only the maps in this folder's parent, so pass this one explicitly. From `catalog/`:

```sh
/usr/bin/python3 validate.py PATH/TO/project-map.yaml
/usr/bin/python3 deploy.py PATH/TO/project-map.yaml --target ~/code/Epicura --plugin
```

An earlier copy of the map lived here until 9 Nov 2026 and named repos that no longer exist. It remains in the git history.
