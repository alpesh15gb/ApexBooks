from app.main import app
import json

schema = app.openapi()
with open('openapi_spec.json', 'w') as f:
    json.dump(schema, f, indent=2)
print(f'OpenAPI spec written: {len(json.dumps(schema))} bytes')
print(f'Total paths: {len(schema["paths"])}')
for path in sorted(schema['paths'].keys()):
    methods = list(schema['paths'][path].keys())
    print(f'  {path}: {" ".join(methods)}')