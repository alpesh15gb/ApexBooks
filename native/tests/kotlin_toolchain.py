"""Use an already installed Kotlin/Gradle compiler for portable native seams."""
from pathlib import Path
import os,subprocess

def add_arguments(parser):
    parser.add_argument('--kotlin-home',type=Path)
    parser.add_argument('--gradle-home',type=Path)

def run_proof(args,sources,directory,main='ProofKt'):
    candidates=[p for p in (args.kotlin_home,args.gradle_home,Path(os.environ['GRADLE_HOME']) if os.environ.get('GRADLE_HOME') else None) if p]
    cache=Path(os.environ.get('GRADLE_USER_HOME',str(Path.home()/'.gradle')))
    candidates.extend(cache.glob('wrapper/dists/gradle-8.14.3-bin/*/gradle-8.14.3'))
    home=next((p for p in candidates if list((p/'lib').glob('kotlin-compiler*.jar'))),None)
    if home is None:raise SystemExit('Use --kotlin-home or --gradle-home for an existing compiler; this check downloads nothing')
    cp=os.pathsep.join(str(p) for p in sorted((home/'lib').glob('*.jar')))
    def run(label,arguments):
        quote=lambda value:'"'+str(value).replace('\\','\\\\').replace('"','\\"')+'"'
        argfile=directory/(label+'.args');argfile.write_text('\n'.join(quote(value) for value in arguments)+'\n',encoding='utf-8')
        subprocess.run([os.environ.get('JAVA','java'),'@'+str(argfile)],check=True)
    jar=directory/'proof.jar'
    run('compile',['-cp',cp,'org.jetbrains.kotlin.cli.jvm.K2JVMCompiler','-no-stdlib','-no-reflect','-classpath',cp,*sources,'-d',jar])
    run('run',['-cp',str(jar)+os.pathsep+cp,main])
