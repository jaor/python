# -*- coding: utf-8 -*-
#pylint: disable=abstract-method
#
# Copyright 2018-2025 BigML
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

"""Base class for PCA' REST calls

   https://bigml.com/api/pcas

"""

try:
    import simplejson as json
except ImportError:
    import json


from bigml.api_handlers.resourcehandler import ResourceHandlerMixin
from bigml.api_handlers.resourcehandler import check_resource_type, \
    resource_is_ready
from bigml.constants import PCA_PATH


class PCAHandlerMixin(ResourceHandlerMixin):
    """This class is used by the BigML class as
       a mixin that provides the REST calls models. It should not
       be instantiated independently.

    """
    def __init__(self):
        """Initializes the PCAHandler. This class is intended
           to be used as a mixin on ResourceHandler, that inherits its
           attributes and basic method from BigMLConnection, and must not be
           instantiated independently.

        """
        self.pca_url = self.url + PCA_PATH

    def create_pca(self, datasets, args=None, wait_time=3, retries=10):
        """Creates a PCA from a `dataset`
           of a list o `datasets`.

        """
        create_args = self._set_create_from_datasets_args(
            datasets, args=args, wait_time=wait_time, retries=retries)

        body = json.dumps(create_args)
        return self._create(self.pca_url, body)

    def get_pca(self, pca, query_string='',
                shared_username=None, shared_api_key=None):
        """Retrieves a PCA.

           The model parameter should be a string containing the
           PCA id or the dict returned by create_pca.
           As a PCA is an evolving object that is processed
           until it reaches the FINISHED or FAULTY state, the function will
           return a dict that encloses the PCA
           values and state info available at the time it is called.

           If this is a shared PCA, the username and
           sharing api key must also be provided.
        """
        check_resource_type(pca, PCA_PATH,
                            message="A PCA id is needed.")
        return self.get_resource(pca,
                                 query_string=query_string,
                                 shared_username=shared_username,
                                 shared_api_key=shared_api_key)

    def pca_is_ready(self, pca, **kwargs):
        """Checks whether a pca's status is FINISHED.

        """
        check_resource_type(pca, PCA_PATH,
                            message="A PCA id is needed.")
        resource = self.get_pca(pca, **kwargs)
        return resource_is_ready(resource)

    def list_pcas(self, query_string=''):
        """Lists all your PCAs.

        """
        return self._list(self.pca_url, query_string)

    def update_pca(self, pca, changes):
        """Updates a PCA.

        """
        check_resource_type(pca, PCA_PATH,
                            message="A PCA id is needed.")
        return self.update_resource(pca, changes)

    def delete_pca(self, pca, query_string=''):
        """Deletes a PCA.

        """
        check_resource_type(pca, PCA_PATH,
                            message="A PCA id is needed.")
        return self.delete_resource(pca, query_string=query_string)

    def clone_pca(self, pca,
                  args=None, wait_time=3, retries=10):
        """Creates a cloned PCA from an existing `PCA`

        """
        create_args = self._set_clone_from_args(
            pca, "pca", args=args, wait_time=wait_time,
            retries=retries)

        body = json.dumps(create_args)
        return self._create(self.pca_url, body)
