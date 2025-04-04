# -*- coding: utf-8 -*-
#
# Copyright 2012-2025 BigML
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

"""An local Fusion object.

This module defines a Fusion to make predictions locally using its
associated models.

This module can help you enormously to
reduce the latency for each prediction and let you use your models
offline.

from bigml.api import BigML
from bigml.fusion import Fusion

# api connection
api = BigML(storage='./storage')

# creating fusion
fusion = api.create_fusion(['model/5143a51a37203f2cf7000972',
                            'model/5143a51a37203f2cf7000985'])

# Fusion object to predict
fusion = Fusion(fusion, api)
fusion.predict({"petal length": 3, "petal width": 1})

"""
import logging

from functools import cmp_to_key
from copy import deepcopy

from bigml.api import get_fusion_id, get_resource_type, \
    get_api_connection
from bigml.model import parse_operating_point, sort_categories
from bigml.model import LAST_PREDICTION
from bigml.basemodel import get_resource_dict
from bigml.multivotelist import MultiVoteList
from bigml.util import cast, check_no_missing_numerics, use_cache, load, \
    dump, dumps, NUMERIC
from bigml.constants import DECIMALS
from bigml.supervised import SupervisedModel
from bigml.modelfields import ModelFields
from bigml.tree_utils import add_distribution



LOGGER = logging.getLogger('BigML')
OPERATING_POINT_KINDS = ["probability"]
LOCAL_SUPERVISED = ["model", "ensemble", "logisticregression", "deepnet",
                    "linearregression", "fusion"]


def rearrange_prediction(origin_classes, destination_classes, prediction):
    """Rearranges the probabilities in a compact array when the
       list of classes in the destination resource does not match the
       ones in the origin resource.

    """
    new_prediction = []
    for class_name in destination_classes:
        try:
            origin_index = origin_classes.index(class_name)
            new_prediction.append(prediction[origin_index])
        except ValueError:
            new_prediction.append(0.0)
    return new_prediction


def get_models_weight(models_info):
    """Parses the information about model ids and weights in the `models`
    key of the fusion dictionary. The contents of this key can be either
    list of the model IDs or a list of dictionaries with one entry per
    model.

    """
    model_ids = []
    weights = []
    try:
        model_info = models_info[0]
        if isinstance(model_info, dict):
            try:
                model_ids = [model["id"] for model in models_info]
            except KeyError:
                raise ValueError("The fusion information does not contain the"
                                 " model ids.")
            try:
                weights = [model["weight"] for model in models_info]
            except KeyError:
                weights = None
        else:
            model_ids = models_info
            weights = None
        if weights is None:
            weights = [1] * len(model_ids)
        return model_ids, weights
    except KeyError:
        raise ValueError("Failed to find the models in the fusion info.")


class Fusion(ModelFields):
    """A local predictive Fusion.

       Uses a number of BigML remote models to build local version of a fusion
       that can be used to generate predictions locally.
       The expected arguments are:

       fusion: fusion object or id
       api: connection object. If None, a new connection object is
            instantiated.
       max_models: integer that limits the number of models instantiated and
                   held in memory at the same time while predicting. If None,
                   no limit is set and all the fusion models are
                   instantiated and held in memory permanently.
       cache_get: user-provided function that should return the JSON
                  information describing the model or the corresponding
                  Model object. Can be used to read these objects from a
                  cache storage.
    """

    def __init__(self, fusion, api=None, max_models=None, cache_get=None,
                 operation_settings=None):

        if use_cache(cache_get):
            # using a cache to store the model attributes
            self.__dict__ = load(get_fusion_id(fusion), cache_get)
            self.api = get_api_connection(api)
            self.operation_settings = operation_settings
            return

        self.resource_id = None
        self.name = None
        self.description = None
        self.models_ids = None
        self.objective_id = None
        self.distribution = None
        self.models_splits = []
        self.cache_get = None
        self.regression = False
        self.fields = None
        self.class_names = None
        self.importance = {}
        self.api = get_api_connection(api)

        self.resource_id, fusion = get_resource_dict( \
            fusion,
            "fusion", api=self.api)

        if 'object' in fusion:
            fusion = fusion.get('object', {})
        try:
            self.name = fusion.get('name')
            self.description = fusion.get('description')
        except AttributeError:
            raise ValueError("Failed to find the expected "
                             "JSON structure. Check your arguments.")

        self.model_ids, self.weights = get_models_weight( \
            fusion['models'])
        model_types = [get_resource_type(model) for model in self.model_ids]

        for model_type in model_types:
            if model_type not in LOCAL_SUPERVISED:
                raise ValueError("The resource %s has not an allowed"
                                 " supervised model type." % model_type)
        self.importance = fusion.get('importance', [])
        self.missing_numerics = fusion.get('missing_numerics', True)
        if fusion.get('fusion'):
            self.fields = fusion.get( \
                'fusion', {}).get("fields")
            self.objective_id = fusion.get("objective_field")
        self.input_fields = fusion.get("input_fields")

        number_of_models = len(self.model_ids)

        # Downloading the model information to cache it
        if self.api.storage is not None or cache_get is not None:
            # adding shared_ref to the API info when donwloading children
            api = self.api
            if self.resource_id.startswith("shared"):
                api = deepcopy(api)
                api.shared_ref = self.resource_id.replace("shared/", "")
            elif hasattr(api, "shared_ref") and \
                    api.shared_ref is not None:
                api = deepcopy(api)
                # adding the resource ID to the sharing chain
                api.shared_ref += ",%s" % self.resource_id
            for model_id in self.model_ids:
                if get_resource_type(model_id) == "fusion":
                    Fusion(model_id, api=api, cache_get=cache_get,
                           operation_settings=operation_settings)
                else:
                    SupervisedModel(model_id, api=api,
                                    cache_get=cache_get,
                                    operation_settings=operation_settings)

        if max_models is None:
            self.models_splits = [self.model_ids]
        else:
            self.models_splits = [self.model_ids[index:(index + max_models)]
                                  for index
                                  in range(0, number_of_models, max_models)]


        ModelFields.__init__( \
            self, self.fields,
            objective_id=self.objective_id)

        add_distribution(self)
        summary = self.fields[self.objective_id]['summary']
        if 'bins' in summary:
            distribution = summary['bins']
        elif 'counts' in summary:
            distribution = summary['counts']
        elif 'categories' in summary:
            distribution = summary['categories']
            self.objective_categories = [
                category for category, _ in distribution]
            self.class_names = sorted(
                self.objective_categories)
        else:
            distribution = []
        self.distribution = distribution
        self.regression = \
            self.fields[self.objective_id].get('optype') == NUMERIC

    def list_models(self):
        """Lists all the model/ids that compound the fusion.

        """
        return self.model_ids

    def predict_probability(self, input_data,
                            missing_strategy=LAST_PREDICTION,
                            compact=False):

        """For classification models, Predicts a probability for
        each possible output class, based on input values.  The input
        fields must be a dictionary keyed by field name or field ID.

        For regressions, the output is a single element
        containing the prediction.

        :param input_data: Input data to be predicted
        :param missing_strategy: LAST_PREDICTION|PROPORTIONAL missing strategy
                                 for missing fields
        :param compact: If False, prediction is returned as a list of maps, one
                        per class, with the keys "prediction" and "probability"
                        mapped to the name of the class and it's probability,
                        respectively.  If True, returns a list of probabilities
                        ordered by the sorted order of the class names.
        """
        votes = MultiVoteList([])
        if not self.missing_numerics:
            check_no_missing_numerics(input_data, self.model_fields)

        weights = []
        for models_split in self.models_splits:
            models = []
            for model in models_split:
                model_type = get_resource_type(model)
                if model_type == "fusion":
                    models.append(Fusion(model, api=self.api))
                else:
                    models.append(SupervisedModel(model, api=self.api))
            votes_split = []
            for model in models:
                try:
                    kwargs = {"compact": True}
                    if model_type in ["model", "ensemble", "fusion"]:
                        kwargs.update({"missing_strategy": missing_strategy})
                    prediction = model.predict_probability( \
                        input_data, **kwargs)
                except ValueError:
                    # logistic regressions can raise this error if they
                    # have missing_numerics=False and some numeric missings
                    # are found
                    continue
                if self.regression:
                    prediction = prediction[0]
                weights.append(self.weights[self.model_ids.index(
                    model.resource_id)])
                prediction = self.weigh(prediction, model.resource_id)
                # we need to check that all classes in the fusion
                # are also in the composing model
                if not self.regression and \
                        self.class_names != model.class_names:
                    try:
                        prediction = rearrange_prediction( \
                            model.class_names,
                            self.class_names,
                            prediction)
                    except AttributeError:
                        # class_names should be defined, but just in case
                        pass
                votes_split.append(prediction)
            votes.extend(votes_split)
        if self.regression:
            prediction = 0
            total_weight = sum(weights)
            for index, pred in enumerate(votes.predictions):
                prediction += pred # the weight is already considered in pred
            if total_weight > 0:
                prediction /= float(total_weight)
            if compact:
                output = [prediction]
            else:
                output = {"prediction": prediction}
        else:
            output = votes.combine_to_distribution(normalize=True)
            if not compact:
                output = [{'category': class_name,
                           'probability': probability}
                          for class_name, probability in
                          zip(self.class_names, output)]

        return output

    def predict_confidence(self, input_data,
                           missing_strategy=LAST_PREDICTION,
                           compact=False):

        """For classification models, Predicts a confidence for
        each possible output class, based on input values.  The input
        fields must be a dictionary keyed by field name or field ID.

        For regressions, the output is a single element
        containing the prediction and the associated confidence.

        WARNING: Only decision-tree based models in the Fusion object will
        have an associated confidence, so the result for fusions that don't
        contain such models can be None.

        :param input_data: Input data to be predicted
        :param missing_strategy: LAST_PREDICTION|PROPORTIONAL missing strategy
                                 for missing fields
        :param compact: If False, prediction is returned as a list of maps, one
                        per class, with the keys "prediction" and "confidence"
                        mapped to the name of the class and it's confidence,
                        respectively.  If True, returns a list of confidences
                        ordered by the sorted order of the class names.
        """
        if not self.missing_numerics:
            check_no_missing_numerics(input_data, self.model_fields)

        predictions = []
        weights = []
        for models_split in self.models_splits:
            models = []
            for model in models_split:
                model_type = get_resource_type(model)
                if model_type == "fusion":
                    models.append(Fusion(model, api=self.api))
                else:
                    models.append(SupervisedModel(model, api=self.api))
            votes_split = []
            for model in models:
                try:
                    kwargs = {"compact": False}
                    if model_type in ["model", "ensemble", "fusion"]:
                        kwargs.update({"missing_strategy": missing_strategy})
                    prediction = model.predict_confidence( \
                        input_data, **kwargs)
                except Exception as exc:
                    # logistic regressions can raise this error if they
                    # have missing_numerics=False and some numeric missings
                    # are found and Linear Regressions have no confidence
                    continue
                predictions.append(prediction)
                weights.append(self.weights[self.model_ids.index(
                    model.resource_id)])
                if self.regression:
                    prediction = prediction["prediction"]
        if self.regression:
            prediction = 0
            confidence = 0
            total_weight = sum(weights)
            for index, pred in enumerate(predictions):
                prediction += pred.get("prediction")  * weights[index]
                confidence += pred.get("confidence")
            if total_weight > 0:
                prediction /= float(total_weight)
                confidence /= float(len(predictions))
            if compact:
                output = [prediction, confidence]
            else:
                output = {"prediction": prediction, "confidence": confidence}
        else:
            output = self._combine_confidences(predictions)
            if not compact:
                output = [{'category': class_name,
                           'confidence': confidence}
                          for class_name, confidence in
                          zip(self.class_names, output)]
        return output

    def _combine_confidences(self, predictions):
        """Combining the confidences per class of classification models"""
        output = []
        count = float(len(predictions))
        for class_name in self.class_names:
            confidence = 0
            for prediction in predictions:
                for category_info in prediction:
                    if category_info["category"] == class_name:
                        confidence += category_info.get("confidence")
                        break
            output.append(round(confidence / count, DECIMALS))
        return output

    def weigh(self, prediction, model_id):
        """Weighs the prediction according to the weight associated to the
        current model in the fusion.

        """
        if isinstance(prediction, list):
            for index, probability in enumerate(prediction):
                probability *= self.weights[ \
                        self.model_ids.index(model_id)]
                prediction[index] = probability
        else:
            prediction *= self.weights[self.model_ids.index(model_id)]

        return prediction

    def predict(self, input_data, missing_strategy=LAST_PREDICTION,
                operating_point=None, full=False):
        """Makes a prediction based on a number of field values.

        input_data: Input data to be predicted
        missing_strategy: LAST_PREDICTION|PROPORTIONAL missing strategy for
                          missing fields
        operating_point: In classification models, this is the point of the
                         ROC curve where the model will be used at. The
                         operating point can be defined in terms of:
                         - the positive_class, the class that is important to
                           predict accurately
                         - the threshold,
                           the value that is stablished
                           as minimum for the positive_class to be predicted.
                         - the kind of measure used to set a threshold:
                           probability or confidence (if available)
                         The operating_point is then defined as a map with
                         two attributes, e.g.:
                           {"positive_class": "Iris-setosa",
                            "threshold": 0.5,
                            "kind": "probability"}
        full: Boolean that controls whether to include the prediction's
              attributes. By default, only the prediction is produced. If set
              to True, the rest of available information is added in a
              dictionary format. The dictionary keys can be:
                  - prediction: the prediction value
                  - probability: prediction's probability
                  - unused_fields: list of fields in the input data that
                                   are not being used in the model
        """

        # Checks and cleans input_data leaving the fields used in the model
        unused_fields = []
        new_data = self.filter_input_data( \
            input_data,
            add_unused_fields=full)
        if full:
            input_data, unused_fields = new_data
        else:
            input_data = new_data

        if not self.missing_numerics:
            check_no_missing_numerics(input_data, self.model_fields)

        # Strips affixes for numeric values and casts to the final field type
        cast(input_data, self.fields)

        full_prediction = self._predict( \
            input_data, missing_strategy=missing_strategy,
            operating_point=operating_point,
            unused_fields=unused_fields)
        if full:
            return dict((key, value) for key, value in \
                full_prediction.items() if value is not None)

        return full_prediction['prediction']

    def _predict(self, input_data, missing_strategy=LAST_PREDICTION,
                 operating_point=None, unused_fields=None):
        """Makes a prediction based on a number of field values. Please,
        note that this function does not check the types for the input
        provided, so it's unsafe to use it directly without prior checking.

        """
        # When operating_point is used, we need the probabilities
        # of all possible classes to decide, so se use
        # the `predict_probability` method
        if operating_point is None and self.operation_settings is not None:
            operating_point = self.operation_settings.get("operating_point")

        if operating_point:
            if self.regression:
                raise ValueError("The operating_point argument can only be"
                                 " used in classifications.")
            prediction = self.predict_operating( \
                input_data,
                missing_strategy=missing_strategy,
                operating_point=operating_point)
            return prediction
        result = self.predict_probability( \
            input_data,
            missing_strategy=missing_strategy,
            compact=False)
        confidence_result = self.predict_confidence( \
            input_data,
            missing_strategy=missing_strategy,
            compact=False)

        if not self.regression:
            try:
                for index, value in enumerate(result):
                    result[index].update(
                        {"confidence": confidence_result[index]["confidence"]})
            except Exception as exc:
                pass
            result = sorted(result, key=lambda x: - x["probability"])[0]
            result["prediction"] = result["category"]
            del result["category"]
        else:
            result.update(
                {"confidence": confidence_result["confidence"]})

        # adding unused fields, if any
        if unused_fields:
            result.update({'unused_fields': unused_fields})

        return result

    def predict_operating(self, input_data,
                          missing_strategy=LAST_PREDICTION,
                          operating_point=None):
        """Computes the prediction based on a user-given operating point.

        """
        if operating_point is None and self.operation_settings is not None:
            operating_point = self.operation_settings.get("operating_point")

        # only probability is allowed as operating kind
        operating_point.update({"kind": "probability"})
        kind, threshold, positive_class = parse_operating_point( \
            operating_point, OPERATING_POINT_KINDS, self.class_names,
            self.operation_settings)
        predictions = self.predict_probability(input_data,
                                               missing_strategy, False)

        position = self.class_names.index(positive_class)
        if predictions[position][kind] > threshold:
            prediction = predictions[position]
        else:
            # if the threshold is not met, the alternative class with
            # highest probability or confidence is returned
            predictions.sort( \
                key=cmp_to_key( \
                lambda a, b: self._sort_predictions(a, b, kind)))
            prediction = predictions[0: 2]
            if prediction[0]["category"] == positive_class:
                prediction = prediction[1]
            else:
                prediction = prediction[0]
        prediction["prediction"] = prediction["category"]
        del prediction["category"]
        return prediction

    #pylint: disable=locally-disabled,invalid-name
    def _sort_predictions(self, a, b, criteria):
        """Sorts the categories in the predicted node according to the
        given criteria

        """
        if a[criteria] == b[criteria]:
            return sort_categories(a, b, self.objective_categories)
        return 1 if b[criteria] > a[criteria] else -1

    def dump(self, output=None, cache_set=None):
        """Uses msgpack to serialize the resource object
        If cache_set is filled with a cache set method, the method is called

        """
        self_vars = vars(self)
        del self_vars["api"]
        dump(self_vars, output=output, cache_set=cache_set)

    def dumps(self):
        """Uses msgpack to serialize the resource object to a string

        """
        self_vars = vars(self)
        del self_vars["api"]
        dumps(self_vars)
