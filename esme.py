
import sys
import os
import argparse
import shutil
import yaml
import tarfile
import subprocess as sp
import datetime as dt
from contextlib import contextmanager
from urllib.parse import urlparse
from jinja2 import Template
from yamanifest import manifest as mf
from pathlib import Path
from git import Repo


@contextmanager
def working_directory(directory):
    owd = os.getcwd()
    try:
        os.chdir(directory)
        yield directory
    finally:
        os.chdir(owd)


def guess_machine():

    import socket
    hostnames = [socket.gethostname()]
    try:
        hostname = os.environ['HOSTNAME']
        hostnames.append(hostname)
    except KeyError:
        pass
    for h in hostnames:
        if 'gadi' in h:
            return 'Gadi'
        for part in ['irsdev', 'irsweb']:
            if part in h:
                return 'SDC'


class Experiment:

    def __init__(self, args):

        self.args = args
        self.name = args.name
        self.path = Path(self.name)

        self.spec_dir = ((Path(__file__).parent).resolve()) / 'experiment_specifications'
        self.config_file = self.path / 'config.yaml'
        settings_file = ((Path(__file__).parent).resolve()) / 'settings.yaml'

        with open (settings_file) as f:
            self.settings = yaml.safe_load(f)


    def __load_config(self):

        self.config_file = self.path / 'config.yaml'
        with open(self.config_file) as f:
            self.config = yaml.safe_load(f)

        return self.config, self.config_file


    def __render_config(self, input_config, output_config, machine_name):

        with open(input_config) as f:

            today = dt.datetime.today().strftime('%Y-%m-%d')
            yesterday = (dt.datetime.today() - dt.timedelta(days=1)).strftime('%Y-%m-%d')
            base_dir = Path(output_config).parent.resolve()

            esme_bucket_cache = None
            for site in self.settings['site']:
                if site['machine_name'] == machine_name:
                    esme_bucket_cache = site['esme_bucket_cache']
            assert esme_bucket_cache is not None
            esme_install_path = (Path(__file__).parent).resolve()

            t = Template(f.read())
            config = t.render(name=self.name,
                              today=today, yesterday=yesterday,
                              base_dir=base_dir,
                              esme_bucket_cache=esme_bucket_cache,
                              machine_name=machine_name,
                              esme_install_path=esme_install_path)

        with open(output_config, 'w') as f:
            print(config, file=f)


    def create(self):
        """
        Create a new case based on an experiment specification/template.

        This step goes from a simple config to a populated experiment
        directory.

        1. Perform some simple substitution on the top-level config, e.g.
           replace {{today}} with today's date.
        2. Download referenced repositories
        3. Create a git repo (or branch) to track this config
        """

        os.makedirs(self.path, exist_ok=True)

        if self.args.machine is None:
            machine_name = guess_machine()
        else:
            machine_name = self.args.machine

        template_dir = self.spec_dir / self.args.template
        assert template_dir.exists()
        self.__render_config(template_dir / 'config.yaml',
                             self.config_file, machine_name)

        config, _ = self.__load_config()
        code_url = config['code_repository_url']
        code_hash = config['code_commit_hash']

        # Get repo and update submodules.
        repo = Repo.init(self.path)
        if repo.is_dirty():
            print('No action. Experiment "{}" exists and has local changes.'.format(self.name))
            return 0

        if 'origin' not in repo.remotes:
            origin = repo.create_remote('origin', code_url)
        else:
            origin = repo.remotes['origin']
        origin.fetch()
        head = repo.create_head('main', origin.refs.main).set_tracking_branch(origin.refs.main)
        head.checkout()

        repo.git.checkout(code_hash)
        for submodule in repo.submodules:
            submodule.update(init=True)



    def __populate_w_manifest(self, manifest_yaml, bucket_url):

        # Read, render and write out
        with open(manifest_yaml) as r:
            t = Template(r.read())
        s = t.render(bucket_url=bucket_url)
        # Write out
        with open(manifest_yaml, 'w') as r:
            r.write(s)

        # Use manifest to populate directory
        imf = mf.Manifest(manifest_yaml).load()
        for filepath in imf:
            url = urlparse(imf.fullpath(filepath))
            assert url.scheme == 'file'
            url = Path(url.path)

            if url.suffix == '.tgz':
                tgz = tarfile.open(url)
                tgz.extractall(manifest_yaml.parent.parent)
                tgz.close()
            else:
                try:
                    os.symlink(url, manifest_yaml.parent / filepath)
                except FileExistsError:
                    pass


    def setup(self):
        """
        Set-up a created case.

        This step prepares the case directory for a build or run. After this
        the model is fully configured and ready to go.

        This will read the case config and perform the following:
        1. Using the file/exe manifests copy or symlink static inputs and
           pre-made build/spack dir (if they exist) into place.
        2. Run local setup.sh script
        """

        assert Path(self.path).exists()
        config, config_file = self.__load_config()

        # FIXME: perhaps the following two steps should be part of the 'create' step?
        # Why put them here.
        # Populate the static data directory. We first need to render the manifest.
        input_manifest = self.path / 'input' / 'input_manifest.yaml'
        self.__populate_w_manifest(input_manifest, config['site']['bucket_url'])

        # Optionally bring in a premade build directory
        build_manifest = self.path / 'build' / 'build_manifest.yaml'
        self.__populate_w_manifest(build_manifest, config['site']['bucket_url'])

        # Bring in the load_env.sh and build.sh for this site:
        machine_name = config['site']['machine_name']
        load_env_tmpl = self.path / 'templates' / 'site' / 'load_env.sh.{}.template'.format(machine_name)
        self.__render_config(load_env_tmpl,
                             self.path / 'load_env.sh', machine_name)

        # FIXME: is it really necessary to have these scripts in the config.yaml?
        # The user is unlikely to change these.
        build_tmpl = self.path / 'templates' / 'site' / 'build.sh.{}.template'.format(machine_name)
        shutil.copy(build_tmpl, self.path / config['build']['build_script'])

        setup_tmpl = self.path / 'templates' / 'site' / 'setup.sh.{}.template'.format(machine_name)
        shutil.copy(setup_tmpl, self.path / config['setup']['setup_script'])

        run_tmpl = self.path / 'templates' / 'site' / 'run.sh.{}.template'.format(machine_name)
        shutil.copy(run_tmpl, self.path / config['run']['run_script'])

        # Execute the model-specific setup script
        with working_directory(self.path):
            r = sp.run(['./' + config['setup']['setup_script']])


    def clone(self):
        pass


    def build(self):
        """
        Invoke build script.
        """

        assert Path(args.name).exists()

        self.__load_config()

        build_script = Path(args.name) / self.config['build_script']
        r = sp.subprocess(build_script)
        assert r == 0


    def list_run_steps(self):
        """
        List all of the available run steps for this case/experiment.
        """

        assert Path(args.name / workflows).exists()


    def run(self):
        """
        Run the experiment/case.

        1. Update file manifests (inputs and exes) - will include recalculating
           hashes.
        2. Lock case so now new configuration changes can be made. This
           includes doing a 'git commit' and perhaps a 'git push'.
        3. Load run environment.
        4. Execute snakefile. This could be the whole thing or a single step.
        """

        assert Path(self.path).exists()
        config, config_file = self.__load_config()

        with working_directory(self.path):
            r = sp.run(['./' + config['run']['run_script']], shell=True)



# FIXME:
def create(args):
    exp = Experiment(args)
    return exp.create()

def setup(args):
    exp = Experiment(args)
    return exp.setup()

def build(args):
    exp = Experiment(args)
    return exp.build()

def run(args):
    exp = Experiment(args)
    return exp.run()

def verify(args):
    pass

def freeze(args):
    pass

def publish(args):
    pass

def clone(args):
    pass


def main():

    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest='subparser_name')
    parser_create = subparsers.add_parser('create')
    parser_create.add_argument('--name', required=True)
    parser_create.add_argument('--template', required=True)
    parser_create.add_argument('--machine', default=None)
    parser_create.set_defaults(func=create)

    parser_setup = subparsers.add_parser('setup')
    parser_setup.add_argument('--name', required=True)
    parser_setup.set_defaults(func=setup)

    parser_build = subparsers.add_parser('build')
    parser_build.add_argument('--name', required=True)
    parser_build.set_defaults(func=build)

    parser_clone = subparsers.add_parser('clone')
    parser_clone.add_argument('--name', required=True)
    parser_clone.add_argument('--parent', required=True)
    parser_clone.set_defaults(func=clone)

    parser_run = subparsers.add_parser('list_run_steps')
    parser_run.add_argument('--name', required=True)
    parser_run.set_defaults(func=run)

    parser_run = subparsers.add_parser('run')
    parser_run.add_argument('--name', required=True)
    parser_run.add_argument('--step')
    parser_run.set_defaults(func=run)

    parser_verify = subparsers.add_parser('verify')
    parser_verify.add_argument('--name', required=True)
    parser_verify.set_defaults(func=verify)

    parser_freeze = subparsers.add_parser('freeze')
    parser_freeze.add_argument('--name', required=True)
    parser_freeze.add_argument('--step')
    parser_freeze.set_defaults(func=freeze)

    parser_publish = subparsers.add_parser('publish')
    parser_publish.add_argument('--name', required=True)
    parser_publish.set_defaults(func=publish)

    args = parser.parse_args()

    if args.subparser_name is None:
        parser.print_help()
        return 1

    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())
