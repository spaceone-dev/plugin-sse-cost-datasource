import logging
from datetime import datetime

from spaceone.core import utils
from spaceone.core.manager import BaseManager
from spaceone.cost_analysis.error import *
from spaceone.cost_analysis.connector.sse_billing_connector import SSEBillingConnector
from spaceone.cost_analysis.model.cost_model import Cost

_LOGGER = logging.getLogger(__name__)

_PROVIDER_MAP = {
    'AWS': 'aws',
    'AWS-China': 'aws_china',
    'GCP': 'google_cloud',
    'AZURE': 'azure',
    'Azure-China': 'azure_china',
    'SPC': 'spc',
    'IDC': 'idc',
}


class CostManager(BaseManager):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sse_connector: SSEBillingConnector = self.locator.get_connector('SSEBillingConnector')

    def get_data(self, options, secret_data, schema, task_options):
        self.sse_connector.create_session(options, secret_data, schema)
        self._check_task_options(task_options)

        signed_url = task_options['signed_url']

        response_stream = self.sse_connector.get_cost_data(signed_url)
        for results in response_stream:
            yield self._make_cost_data(results)

    @staticmethod
    def _make_cost_data(results):
        costs_data = []

        """ Source Data Model
        class CostSummaryItem(BaseModel):
            usage_date: str
            infra_type: str
            account_id: str
            account_name: str
            category_name: str
            sub_category_name: str
            product_service_code: str
            product_region: str
            resource_cost: float
            service_id: str
            usage_quantity: float
            usage_type: str
        """

        for result in results:
            try:
                data = {
                    'cost': result['resource_cost'],
                    'currency': result.get('currency', 'USD'),
                    'usage_quantity': result.get('usage_quantity', 0),
                    'provider': _PROVIDER_MAP.get(result['infra_type'], result['infra_type']),
                    'region_code': result.get('product_region'),
                    'category': result.get('category_name'),
                    'resource_group': result.get('sub_category_name'),
                    'product': result.get('product_service_code'),
                    'account': str(result['account_id']),
                    'usage_type': result.get('usage_type'),
                    'billed_at': datetime.strptime(result['usage_date'], '%Y-%m-%d')
                }
            except Exception as e:
                _LOGGER.error(f'[_make_cost_data] make data error: {e}', exc_info=True)
                raise e

            costs_data.append(data)

            # Excluded because schema validation is too slow
            # cost_data = Cost(data)
            # cost_data.validate()
            #
            # costs_data.append(cost_data.to_primitive())

        return costs_data

    @staticmethod
    def _check_task_options(task_options):
        if 'billing_year' not in task_options:
            raise ERROR_REQUIRED_PARAMETER(key='task_options.billing_year')

        if 'billing_month' not in task_options:
            raise ERROR_REQUIRED_PARAMETER(key='task_options.billing_month')
