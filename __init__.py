# This file is part production_operation_alert module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
from trytond.pool import Pool

from . import alert

def register():
    Pool.register(
        alert.OperationAlert,
        alert.Work,
        alert.WorkCycle,
        alert.Cron,
        module='production_operation_alert', type_='model')
    Pool.register(
        module='production_operation_alert', type_='wizard')
    Pool.register(
        module='production_operation_alert', type_='report')
