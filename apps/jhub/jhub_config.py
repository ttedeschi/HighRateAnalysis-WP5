#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import socket
import json
# from oauthenticator.github import GitHubOAuthenticator
from oauthenticator.oauth2 import OAuthenticator
from oauthenticator.generic import GenericOAuthenticator
from tornado import gen
import kubespawner
import subprocess
import warnings

import os

from subprocess import check_call

c.JupyterHub.tornado_settings = {
    'max_body_size': 1048576000, 'max_buffer_size': 1048576000}
c.JupyterHub.log_level = 30

callback = os.environ["OAUTH_CALLBACK_URL"]
os.environ["OAUTH_CALLBACK"] = callback
iam_server = os.environ["OAUTH_ENDPOINT"]

server_host = socket.gethostbyname(socket.getfqdn())
os.environ["IAM_INSTANCE"] = iam_server

myenv = os.environ.copy()

c.Spawner.default_url = '/lab'

cache_file = './iam_secret'

if os.path.isfile(cache_file):
    with open(cache_file) as f:
        cache_results = json.load(f)
else:
    response = subprocess.check_output(
        ['/srv/.init/dodas-IAMClientRec', server_host+"-jhub"], env=myenv)
    response_list = response.decode('utf-8').split("\n")
    client_id = response_list[len(response_list)-3]
    client_secret = response_list[len(response_list)-2]

    cache_results = {
        "client_id": server_host+"-jhub",
        "client_secret": "testmepls"
    }
    with open(cache_file, "w") as w:
        json.dump(cache_results, w)

client_id = cache_results["client_id"]
client_secret = cache_results["client_secret"]


class EnvAuthenticator(GenericOAuthenticator):

    @gen.coroutine
    def pre_spawn_start(self, user, spawner):
        auth_state = yield user.get_auth_state()
        import pprint
        pprint.pprint(auth_state)
        if not auth_state:
            # user has no auth state
            return
        # define some environment variables from auth_state
        self.log.info(auth_state)
        spawner.environment['IAM_SERVER'] = iam_server
        spawner.environment['IAM_CLIENT_ID'] = "<iam client id>"
        spawner.environment['IAM_CLIENT_SECRET'] = "<iam client secret>"
        spawner.environment['ACCESS_TOKEN'] = auth_state['access_token']
        spawner.environment['REFRESH_TOKEN'] = auth_state['refresh_token']
        spawner.environment['MINIO_AUDIENCE'] = os.environ.get(
            "MINIO_AUDIENCE")
        spawner.environment['TUNNEL_SERVICE_PORT'] = os.environ.get(
            "TUNNEL_SERVICE_PORT")
        spawner.environment['USERNAME'] = auth_state['oauth_user']['preferred_username']
        spawner.environment['JUPYTERHUB_ACTIVITY_INTERVAL'] = "15"
        spawner.environment['SSH_NAMESPACE'] = os.environ.get("SSH_NAMESPACE")

        amIAllowed = False

        import jwt
        groups = jwt.decode(auth_state["access_token"], options={
                            "verify_signature": False, "verify_aud": False})["wlcg.groups"]

        if os.environ.get("OAUTH_GROUPS"):
            spawner.environment['GROUPS'] = " ".join(groups)
            allowed_groups = os.environ["OAUTH_GROUPS"].split(" ")
            self.log.info(groups)
            for gr in allowed_groups:
                if gr in groups:
                    amIAllowed = True

            if not amIAllowed:
                self.log.error(
                    "OAuth user contains not in group the allowed groups %s" % allowed_groups
                )
                raise Exception(
                    "OAuth user not in the allowed groups %s" % allowed_groups)

    async def authenticate(self, handler, data=None):
        code = handler.get_argument("code")
        # TODO: Configure the curl_httpclient for tornado
        http_client = self.http_client()

        params = dict(
            redirect_uri=self.get_callback_url(handler),
            code=code,
            grant_type='authorization_code',
        )
        params.update(self.extra_params)

        headers = self._get_headers()

        token_resp_json = await self._get_token(http_client, headers, params)

        user_data_resp_json = await self._get_user_data(http_client, token_resp_json)

        if callable(self.username_key):
            name = self.username_key(user_data_resp_json)
        else:
            name = user_data_resp_json.get(self.username_key)
        if not name:
            self.log.error(
                "OAuth user contains no key %s: %s", self.username_key, user_data_resp_json
            )
            return

        auth_state = self._create_auth_state(
            token_resp_json, user_data_resp_json)
        import pprint
        pprint.pprint(auth_state)

        import jwt
        groups = jwt.decode(auth_state["access_token"], options={
                            "verify_signature": False, "verify_aud": False})["wlcg.groups"]

        pprint.pprint(groups)

        is_admin = False
        if os.environ.get("ADMIN_OAUTH_GROUPS") in groups:
            self.log.info("%s : %s is in %s",
                          (name, os.environ.get("ADMIN_OAUTH_GROUPS"), groups))
            is_admin = True
        else:
            self.log.info(" %s is not in admin group ", name)

        return {
            'name': name,
            'admin': is_admin,
            # self._create_auth_state(token_resp_json, user_data_resp_json)
            'auth_state': auth_state
        }


# c.JupyterHub.authenticator_class = GitHubEnvAuthenticator
c.JupyterHub.authenticator_class = EnvAuthenticator
c.GenericOAuthenticator.oauth_callback_url = callback

# PUT IN SECRET
c.GenericOAuthenticator.client_id = client_id
c.GenericOAuthenticator.client_secret = client_secret
c.GenericOAuthenticator.authorize_url = iam_server.strip('/') + '/authorize'
c.GenericOAuthenticator.token_url = iam_server.strip('/') + '/token'
c.GenericOAuthenticator.userdata_url = iam_server.strip('/') + '/userinfo'
c.GenericOAuthenticator.scope = [
    'openid', 'profile', 'email', 'address', 'offline_access', 'wlcg', 'wlcg.groups']
c.GenericOAuthenticator.username_key = "preferred_username"

c.GenericOAuthenticator.enable_auth_state = True
if 'JUPYTERHUB_CRYPT_KEY' not in os.environ:
    warnings.warn(
        "Need JUPYTERHUB_CRYPT_KEY env for persistent auth_state.\n"
        " export JUPYTERHUB_CRYPT_KEY=$(openssl rand -hex 32)"
    )
    c.CryptKeeper.keys = [os.urandom(32)]


class CustomSpawner(kubespawner.KubeSpawner):
    def _options_form_default(self):
        return """
    <label for="stack">Select your desired image:</label>
    <input list="images" name="img">
    <datalist id="images">
    <option value="ghcr.io/comp-dev-cms-ita/jupyterlab:v2.0.1-patch10-dask">Centos7 base image </option>
    </datalist>
    <br>
    <label for="cpu">Select your desired number of cores:</label>
    <select name="cpu" size="1">
    <option value="1">1</option>
    <option value="2">2</option>
    <option value="4">4</option>
    <option value="8">8</option>
    </select>
    <br>
    <label for="mem">Select your desired memory size:</label>
    <select name="mem" size="1">
    <option value="2G">2GB</option>
    <option value="4G">4GB</option>
    <option value="8G">8GB</option>
    <option value="16G">16GB</option>
    </select>
    <br>

    """

    def options_from_form(self, formdata):
        mem_req_map = {
            "2G": "1800M",
            "4G": "3500M",
            "8G": "6800M",
            "16G": "14G"
        }

        cpu_req_map = {
            "1": "800m",
            "2": "1800m",
            "4": "3500m",
            "8": "6800m"
        }

        options = {}
        options['img'] = formdata['img']
        container_image = ''.join(formdata['img'])
        print("SPAWN: " + container_image + " IMAGE")
        self.image = container_image

        options['cpu'] = formdata['cpu']
        cpu = ''.join(formdata['cpu'])
        self.cpu_guarantee = float(cpu_req_map[cpu])
        self.cpu_limit = float(cpu)

        options['mem'] = formdata['mem']
        memory = ''.join(formdata['mem'])
        self.mem_guarantee = mem_req_map[memory]
        self.mem_limit = memory

        # options['gpu'] = formdata['gpu']
        # use_gpu = True if ''.join(formdata['gpu'])=="Y" else False
        # if use_gpu:
        # self.extra_resource_guarantees = {"nvidia.com/gpu": "1"}
        # self.extra_resource_limit = {"nvidia.com/gpu": "1"}
        return options


c.JupyterHub.spawner_class = CustomSpawner

c.KubeSpawner.cmd = ["/usr/local/bin/jupyterhub-singleuser.sh"]
c.KubeSpawner.args = ["--allow-root", "--ServerApp.jpserver_extensions=ksmm=True",
                      '--FileCheckpoints.checkpoint_dir="/tmp"']
c.KubeSpawner.privileged = True

c.KubeSpawner.extra_pod_config = {
    "automountServiceAccountToken": True,
}

c.KubeSpawner.environment = {
    "_condor_COLLECTOR_HOST": os.environ["HTCONDOR_COLLECTOR_URL"],
    "_condor_SCHEDD_HOST": os.environ["HTCONDOR_SCHEDD_NAME"],
    "_condor_SCHEDD_NAME": os.environ["HTCONDOR_SCHEDD_NAME"],
    "_condor_AUTH_SSL_CLIENT_CAFILE": "/ca.crt",
    "_condor_SEC_DEFAULT_AUTHENTICATION_METHODS": "SCITOKENS",
    "_condor_SCITOKENS_FILE": "/tmp/token",
    "_condor_TOOL_DEBUG": "D_FULLDEBUG,D_SECURITY"
}

c.KubeSpawner.extra_container_config = {
    "securityContext": {
        "privileged": True,
        "capabilities": {
            "add": ["SYS_ADMIN"]
        }
    },
    "imagePullPolicy": "Always"
}
c.KubeSpawner.http_timeout = 600
c.KubeSpawner.start_timeout = 600

c.JupyterHub.hub_connect_ip = 'hub.default.svc.cluster.local'

c.KubeSpawner.notebook_dir = "/opt/workspace"
c.FileCheckpoints.checkpoint_dir = '/tmp'
