"""
Devops tasks: builds, deployments and migrations.

Copyright (c) 2016-present, Facebook, Inc.
All rights reserved.

This source code is licensed under the BSD-style license found in the
LICENSE file in the root directory of this source tree. An additional grant
of patent rights can be found in the PATENTS file in the same directory.
"""

import datetime
import getpass
import json
import time
import os
import datetime

from fabric.api import cd, lcd, local, env, require, run, put, settings
from fabric.utils import abort, warn, puts
from fabric.operations import get, sudo

def update_css():
    """ [dev] Recompile CSS """
    with lcd('react-theme/css'):
        local('pwd')
        local('sass theme.scss > compiled/endaga.css')
        local('cp compiled/endaga.css ../../endagaweb/static/css/endaga.css')

def dev():
    """
    Sets the environment variables to deploy to localhost
    """
    """ Host config for local Vagrant VM. """
    vagrant_machine = "web"
    env.deploy_target = "dev"

    host = local('vagrant ssh-config %s | grep HostName' % (vagrant_machine,),
                     capture=True).split()[1]
    port = local('vagrant ssh-config %s | grep Port' % (vagrant_machine,),
                     capture=True).split()[1]
    env.hosts = ['vagrant@%s:%s' % (host, port)]
    identity_file = local('vagrant ssh-config %s | grep IdentityFile' %
                              (vagrant_machine,), capture=True)
    env.key_filename = identity_file.split()[1].strip('"')
       
def prod():
    """ [deploy] Production deploy settings """
    env.deploy_target = "production"
    env.hosts = ['cereblanco@pcari-vbts.com:30172']

def staging():
    """ [deploy] Staging deploy settings """
    env.deploy_target = "staging"
    env.hosts = ['ccm-admin@127.0.0.1:3022']
    env.password = 'admin@123'

def staff():
    """ [deploy] Staff deploy settings """
    env.deploy_target = "staff"

def proxy():
    """ Use SOCKS proxy for ssh from dev servers """
    env.ssh_config_path = "../client/ssh/proxy-config"
    env.use_ssh_config = True

def _is_hg():
    """ Determines if the project is hg controlled """
    try:
        local("hg identify")
        return True
    except:
        return False

def _is_git():
    """ Determines if the project is git controlled """
    try:
        local("git rev-parse")
        return True
    except:
        return False

def _get_versioning_metadata():
    """ Extracts version metadata from the version control system """
    if _is_hg():
        commit_summary = local('hg id -i', capture=True).translate("+")
        # Extract the current branch/bookmark from the bookmarks list.
        bookmarks = local("hg bookmarks", capture=True)
        branch = "master"
        for line in bookmarks.split("\n"):
            if "*" in line:
                branch = line.split()[1]
                break
    elif _is_git():
        branch = local("git rev-parse --abbrev-ref HEAD", capture=True)
        commit_summary = local('git rev-parse HEAD', capture=True).translate(None, "+")
    else:
        raise Exception("Not git or hg")

    # dpkg requires the version start with a number, so lead with `0-`
    version = "0-%s" % commit_summary.split()[0]
    return branch, commit_summary, version

def package():
    """ [deploy] Creates a deployment package. """
    branch, summary, version = _get_versioning_metadata()

    # Builds the deployment package.
    local('fpm -s dir -t deb -n endagaweb -a all -v %(version)s \
            --description "%(branch)s: %(cs)s" \
            -d byobu -d nginx -d python-pip -d python-dev \
            -d libpq-dev -d git -d supervisor \
            endagaweb=/var/www ../common/ccm=/var/www \
            requirements.txt=/var/opt/ \
            sason=/var/www settings.py=/var/www urls.py=/var/www \
            manage.py=/var/www/ configs/nginx.conf=/etc/nginx/sites-enabled/ \
            configs/uwsgi.conf=/etc/init/ \
            configs/endagaweb.ini=/etc/uwsgi/apps-enabled/ \
            configs/celeryd.conf=/etc/supervisor/conf.d/ \
            configs/celerybeat.conf=/etc/supervisor/conf.d/ \
            configs/celerystick.conf=/etc/supervisor/conf.d/' \
            % {'branch': branch, 'cs': summary, 'version': version})
    return version

def prepdeploy():
    """ [prepdeploy] Create deploy package and push to remote """
    
    local('mkdir -p /tmp/deploydir')
    run('mkdir -p ~/deploydir/packages')
    pkg_version = package()
    pkg_file = "endagaweb_%s_all.deb" % pkg_version
    put('%s' % pkg_file, '~/deploydir/packages/')
    local('rm %s' % pkg_file)
    return pkg_file 

def install_dependencies():
    """ [install_dependecies] Install the needed packages """

    sudo("apt-get update -y")

    sudo("apt-get install -y byobu nginx uwsgi python-pip python-dev " \
         "libpq-dev git supervisor daemontools binutils libproj-dev gdal-bin")
    
    sudo("pip install uwsgi")

def install_endagaweb(deployment_bundle):
    """ Install the application """
    
    sudo("dpkg -i ~/deploydir/packages/%s" % deployment_bundle) 

def install_envdir():
    """ [install_envdir] Install environment variables """

    put("configs/endagaweb-envdir", "~/deploydir/")
    sudo("cp -r ~/deploydir/endagaweb-envdir /var/opt/") 

def start_application():
    """ [start_application] Start application. """
    
    sudo("systemctl start uwsgi")
    sudo("systemctl start nginx")
#     sudo("service nginx start")
#     sudo("service uwsgi start")
    run("touch /tmp/endagaweb-reload")
    if env.deploy_target == "production":
        sudo("supervisorctl start celery")
        sudo("supervisorctl start celerystick")
        sudo("supervisorctl start celerybeat")
    else:
        sudo("supervisorctl stop celery")
        sudo("supervisorctl stop celerystick")
        sudo("supervisorctl stop celerybeat")

def stop_application():
    """ [stop_application] Stop application. """
    
    sudo("systemctl stop nginx")
    sudo("systemctl stop uwsgi")
#     sudo("service nginx stop")
#     sudo("service uwsgi stop")

    sudo("supervisorctl stop celery")
    sudo("supervisorctl stop celerystick")
    sudo("supervisorctl stop celerybeat")

def endagaweb_postinst():
    """ [endagaweb_postinst] Post-install instructions"""
    
    sudo("pip freeze | grep -v -f /var/opt/requirements.txt - | " \
         "grep -v '^#' | grep -v '^-e ' | xargs pip uninstall -y")
    sudo("pip install -r /var/opt/requirements.txt")

    # Collect all the Django static resources into the location nginx expects
    sudo("envdir /var/opt/endagaweb-envdir /var/www/manage.py "
         "collectstatic --noinput")

    # Prepare uwsgi log directory
    sudo("mkdir -p /var/log/uwsgi")
    sudo("chmod -R g+w /var/log/uwsgi")
    sudo("chown -R www-data:www-data /var/log/uwsgi")

    # Prepare celery log directory
    sudo("mkdir -p /var/log/celery")
    sudo("chmod -R g+w /var/log/celery")
    sudo("chown -R www-data:www-data /var/log/celery")
    
    # Remove any default nginx confs
    sudo("rm -f /etc/nginx/sites-enabled/default")
    
    # Restart supervisor
    sudo("supervisorctl update")

def deploy(description=None):
    """ [deploy] Make a deployment to an environment. """
    
    branch, _, _ = _get_versioning_metadata()
    try:
        if env.deploy_target == "production":
            if branch != "master":
                abort("Can't deploy to production from a non-master branch.")
    except AttributeError:
        abort("No deployment target specified.")
    deployment_bundle = prepdeploy()
    if not description:
        now = datetime.datetime.utcnow()
        description = "Deployment of %s at %s UTC" % (deployment_bundle, now)
    # Start the deploy.
    text = 'Start deploying to `%s` from branch `%s` (bundle: `%s`)' % (
        env.deploy_target, branch, deployment_bundle)
    print(text)

    install_dependencies()
    install_endagaweb(deployment_bundle)
    install_envdir()
    start_application()
    endagaweb_postinst() 

def migrate(application="", migration="", fake_initial=""):
    """[deploy] Perform a database migration.

    Use fake_initial when the db structure already exists -- in old versions of
    Django this was run automatically (see the 1.8 docs for more info).

    Usage:
      fab staging migrate:application=endagaweb,fake_initial=True
    """
    branch, _, _ = _get_versioning_metadata()
    try:
        if env.deploy_target == "production":
            if branch != "master":
                abort("Can't deploy to production from a non-master branch.")
    except AttributeError:
        abort("No deployment target specified.")
    cmd = ("/var/www/manage.py migrate %s %s --noinput"
           % (application, migration))
    if fake_initial:
        cmd = '%s --fake-initial' % cmd
    result = sudo("envdir /var/opt/endagaweb-envdir %s" % cmd)

    msg = (("[%s] DB migration to `%s` " % (env.deploy_target, branch)) +
           ("is complete" if result.succeeded else "was unsuccessful"))
    print msg
    
    
def dump_db():
    """[deploy] Perform a database migration."""
  
    date = time.strftime("%Y%m%d-%H%M%S")
    output_name = "endagawebdb_%s.json" % date
    run("mkdir -p ~/backups/db")
    sudo("envdir /var/opt/endagaweb-envdir /var/www/manage.py "
         "dumpdata -v0 --natural-primary --natural-foreign > ~/backups/db/%s"
          % output_name)
    get("~/backups/db/%s" % output_name, output_name)
    
    