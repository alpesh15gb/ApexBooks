from pathlib import Path
required = ['app/main.py','app/api/v1/router.py','docker-compose.yml','Dockerfile','pyproject.toml']
missing=[p for p in required if not Path(p).exists()]
route_files=list(Path('app/api/v1').glob('*/router.py'))
print({'missing': missing, 'router_files': len(route_files), 'routers': [str(p) for p in route_files]})
raise SystemExit(1 if missing else 0)
