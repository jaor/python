# -*- coding: utf-8 -*-
#pylint: disable=abstract-method
#
# Copyright 2015-2025 BigML
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

"""Base class for associations' REST calls

   https://bigml.com/api/associations

"""

try:
    import simplejson as json
except ImportError:
    import json


from bigml.api_handlers.resourcehandler import ResourceHandlerMixin
from bigml.api_handlers.resourcehandler import check_resource_type
from bigml.constants import ASSOCIATION_PATH


class AssociationHandlerMixin(ResourceHandlerMixin):
    """This class is used by the BigML class as
       a mixin that provides the correlations' REST calls. It should not
       be instantiated independently.

    """
    def __init__(self):
        """Initializes the CorrelationHandler. This class is intended to be
           used as a mixin on ResourceHandler, that inherits its
           attributes and basic method from BigMLConnection, and must not be
           instantiated independently.

        """
        self.association_url = self.url + ASSOCIATION_PATH

    def create_association(self, datasets, args=None, wait_time=3, retries=10):
        """Creates an association from a `dataset`.

        """
        create_args = self._set_create_from_datasets_args(
            datasets, args=args, wait_time=wait_time, retries=retries)

        body = json.dumps(create_args)
        return self._create(self.association_url, body)

    def get_association(self, association, query_string=''):
        """Retrieves an association.

           The association parameter should be a string containing the
           association id or the dict returned by create_association.
           As association is an evolving object that is processed
           until it reaches the FINISHED or FAULTY state, the function will
           return a dict that encloses the association values and state info
           available at the time it is called.
        """
        check_resource_type(association, ASSOCIATION_PATH,
                            message="An association id is needed.")
        return self.get_resource(association, query_string=query_string)

    def list_associations(self, query_string=''):
        """Lists all your associations.

        """
        return self._list(self.association_url, query_string)

    def update_association(self, association, changes):
        """Updates a association.

        """
        check_resource_type(association, ASSOCIATION_PATH,
                            message="An association id is needed.")
        return self.update_resource(association, changes)

    def delete_association(self, association, query_string=''):
        """Deletes an association.

        """
        check_resource_type(association, ASSOCIATION_PATH,
                            message="An association id is needed.")
        return self.delete_resource(association, query_string=query_string)

    def clone_association(self, association,
                          args=None, wait_time=3, retries=10):
        """Creates a cloned association from an existing `association`

        """
        create_args = self._set_clone_from_args(
            association, "association", args=args, wait_time=wait_time,
            retries=retries)

        body = json.dumps(create_args)
        return self._create(self.association_url, body)
