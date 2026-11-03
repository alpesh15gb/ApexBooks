"""TEST ONLY PostgreSQL counterpart. Not imported by app/migrations/readiness.

Dedicated preseeded counters do NOT solve arbitrary multi-company transaction
lock ordering. The accompanying test retains that expected failure explicitly.
"""
from sqlalchemy import JSON, inspect, text
from prototype import COVERED, TABLE, schema_check, quote

BUMP = 'poc_bump_generation'

def function_bodies(metadata):
    bodies = {BUMP: f"""BEGIN
 UPDATE public.{TABLE} SET generation=generation+1 WHERE company_id=scope;
 IF NOT FOUND THEN RAISE EXCEPTION 'Missing experimental company generation' USING ERRCODE='23514'; END IF;
END;"""}
    for name in sorted(COVERED):
        key = 'id' if name == 'companies' else 'company_id'
        comparisons = []
        for column in metadata.tables[name].columns:
            old, new = 'OLD.'+quote(column.name), 'NEW.'+quote(column.name)
            # json has no equality operator; text is deliberately conservative:
            # semantically equal differently serialized JSON can invalidate extra.
            if isinstance(column.type, JSON): old += '::text'; new += '::text'
            comparisons.append(f'{old} IS DISTINCT FROM {new}')
        seed = f'INSERT INTO public.{TABLE}(company_id,generation) VALUES(NEW.id,0);' if name == 'companies' else ''
        immutable = "IF OLD.id IS DISTINCT FROM NEW.id THEN RAISE EXCEPTION 'Company identifier reassignment unsupported' USING ERRCODE='23514'; END IF;" if name == 'companies' else ''
        bodies['poc_generation_'+name] = f"""DECLARE domain text;
BEGIN
 IF TG_OP='UPDATE' THEN
  {immutable}
  IF NOT ({' OR '.join(comparisons)}) THEN RETURN NEW; END IF;
  FOR domain IN SELECT DISTINCT value FROM unnest(ARRAY[OLD.{quote(key)},NEW.{quote(key)}]) AS scopes(value) ORDER BY value LOOP
   PERFORM public.{BUMP}(domain);
  END LOOP;
  RETURN NEW;
 ELSIF TG_OP='INSERT' THEN
  {seed}
  PERFORM public.{BUMP}(NEW.{quote(key)});
  RETURN NEW;
 ELSE
  PERFORM public.{BUMP}(OLD.{quote(key)});
  RETURN OLD;
 END IF;
END;"""
    return bodies

def install(connection, metadata):
    if connection.dialect.name != 'postgresql': raise ValueError('PostgreSQL proof only')
    schema_check(connection, metadata)
    connection.exec_driver_sql(f'CREATE TABLE public.{TABLE}(company_id text PRIMARY KEY,generation bigint NOT NULL CHECK(generation>=0 AND generation<9223372036854775807))')
    connection.exec_driver_sql(f'INSERT INTO public.{TABLE}(company_id,generation) SELECT id,0 FROM public.companies')
    for name, body in function_bodies(metadata).items():
        args, result = ('scope text', 'void') if name == BUMP else ('', 'trigger')
        connection.exec_driver_sql(f'CREATE FUNCTION public.{name}({args}) RETURNS {result} LANGUAGE plpgsql SECURITY INVOKER AS $proof${body}$proof$')
    for table in sorted(COVERED):
        for event in ('INSERT','UPDATE','DELETE'):
            name=f'poc_change_{table}_{event.lower()}'
            connection.exec_driver_sql(f'CREATE TRIGGER {quote(name)} AFTER {event} ON public.{quote(table)} FOR EACH ROW EXECUTE FUNCTION public.poc_generation_{table}()')
    readiness(connection, metadata)

def readiness(connection, metadata):
    schema_check(connection, metadata)
    if connection.exec_driver_sql('SHOW session_replication_role').scalar_one() != 'origin':
        raise ValueError('Proof row triggers require origin replication role')
    functions = connection.execute(text("SELECT p.proname,p.prosrc,p.prosecdef,l.lanname,p.pronargs FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace JOIN pg_language l ON l.oid=p.prolang WHERE n.nspname='public' AND (p.proname LIKE :pattern OR p.proname='poc_bump_generation')"), {'pattern': 'poc_generation_%'}).all()
    expected = function_bodies(metadata)
    if len(functions) != len(expected): raise ValueError('Missing or overloaded proof functions')
    for name, body, definer, language, nargs in functions:
        if name not in expected or body.strip()!=expected[name].strip() or definer or language!='plpgsql' or nargs!=(1 if name==BUMP else 0):
            raise ValueError('Changed proof function definition')
    rows=connection.execute(text("SELECT t.tgname,c.relname,t.tgtype,t.tgenabled,p.proname,pn.nspname,t.tgqual,t.tgnargs,t.tgconstraint FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace JOIN pg_proc p ON p.oid=t.tgfoid JOIN pg_namespace pn ON pn.oid=p.pronamespace WHERE n.nspname='public' AND t.tgname LIKE :pattern"), {'pattern': 'poc_change_%'}).all()
    wanted={(f'poc_change_{table}_{event}',table,kind,'O','poc_generation_'+table,'public',None,0,0) for table in COVERED for event,kind in [('insert',5),('update',17),('delete',9)]}
    if set(rows)!=wanted: raise ValueError('Missing or changed proof trigger definition')
    if inspect(connection).get_foreign_keys(TABLE): raise ValueError('Counter must not add a Company FK lock')
    missing=connection.exec_driver_sql(f'SELECT count(*) FROM public.companies c LEFT JOIN public.{TABLE} g ON g.company_id=c.id WHERE g.company_id IS NULL').scalar_one()
    if missing: raise ValueError('Unseeded company generation')

def token(connection, cid):
    return connection.execute(text(f'SELECT generation FROM public.{TABLE} WHERE company_id=:cid'),{'cid':cid}).scalar_one()
