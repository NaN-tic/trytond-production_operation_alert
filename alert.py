# This file is part production_operation_alert module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
import datetime

from trytond.model import ModelSQL, ModelView, fields
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval, If


class OperationAlert(ModelSQL, ModelView):
    'Operation Alert'
    __name__ = 'production.operation.alert'

    line = fields.Many2One(
        'production.work.center', 'Line', required=True,
        domain=[
            ('category.is_line', '=', True),
            ],
        ondelete='RESTRICT')
    work_center = fields.Many2One(
        'production.work.center', 'Work Center', required=True,
        domain=[
            ('parent', 'child_of', [Eval('line', -1)]),
            ],
        depends=['line'],
        ondelete='RESTRICT')
    product = fields.Many2One(
        'product.product', 'Product', required=True, ondelete='CASCADE')
    operation = fields.Many2One(
        'production.routing.operation', 'Operation', required=True,
        ondelete='RESTRICT')
    type = fields.Selection([
            ('time', 'Time'),
            ], 'Type', required=True, sort=False)
    time = fields.Integer(
        'Time', states={
            'required': Eval('type') == 'time',
            'invisible': Eval('type') != 'time',
            },
        depends=['type'],
        help='Time in minutes before the alert is triggered.')
    state = fields.Selection([
            ('ok', 'OK'),
            ('warning', 'Warning'),
            ('danger', 'Danger'),
            ], 'State', required=True, sort=False,
        help='State to set on the work cycle when this alert is triggered.')

    @staticmethod
    def default_type():
        return 'time'

    @staticmethod
    def default_state():
        return 'warning'


class Work(metaclass=PoolMeta):
    __name__ = 'production.work'

    alert_state = fields.Function(fields.Selection([
                ('ok', 'OK'),
                ('warning', 'Warning'),
                ('danger', 'Danger'),
                ], 'Alert State'),
        'get_alert_state')
    alerts = fields.Function(
        fields.One2Many('production.operation.alert', None, 'Alerts'),
        'get_alerts')

    def get_alerts(self, name):
        Alert = Pool().get('production.operation.alert')

        line = self.production.work_center if self.production else None
        work_center = self.work_center
        product = self.production.product if self.production else None
        operation = self.operation
        if not line or not work_center or not product or not operation:
            return []
        alerts = Alert.search([
                ('line', '=', line.id),
                ('work_center', '=', work_center.id),
                ('product', '=', product.id),
                ('operation', '=', operation.id),
                ])
        return [a.id for a in alerts]

    def get_alert_state(self, name):
        states = {cycle.alert_state for cycle in self.cycles if cycle.alert_state}
        if 'danger' in states:
            return 'danger'
        if 'warning' in states:
            return 'warning'
        return 'ok'

    @classmethod
    def view_attributes(cls):
        return super().view_attributes() + [
            ('/tree', 'visual',
                If(Eval('alert_state') == 'danger', 'danger',
                    If(Eval('alert_state') == 'warning', 'warning', '')),
                ['alert_state']),
            ('/tree/field[@name="operation"]', 'visual',
                If(Eval('alert_state') == 'danger', 'danger',
                    If(Eval('alert_state') == 'warning', 'warning', '')),
                ['alert_state']),
            ]


class WorkCycle(metaclass=PoolMeta):
    __name__ = 'production.work.cycle'

    run_date = fields.DateTime('Run Date', readonly=True)
    alert_state = fields.Selection([
            ('ok', 'OK'),
            ('warning', 'Warning'),
            ('danger', 'Danger'),
            ], 'Alert State', readonly=True, sort=False)

    @staticmethod
    def default_alert_state():
        return 'ok'


    @classmethod
    def get_matching_alerts(cls, cycle):
        Alert = Pool().get('production.operation.alert')

        if not cycle.work or not cycle.work.work_center:
            return []
        if (not cycle.work.production or not cycle.work.production.product
                or not cycle.work.production.work_center):
            return []
        operation = cycle.work.operation
        if not operation:
            return []
        return Alert.search([
                ('line', '=', cycle.work.production.work_center.id),
                ('work_center', '=', cycle.work.work_center.id),
                ('product', '=', cycle.work.production.product.id),
                ('operation', '=', operation.id),
                ])

    @classmethod
    def compute_alert_state(cls, cycle, now=None):
        if now is None:
            now = datetime.datetime.now()
        if cycle.state != 'running':
            return 'ok'

        states = []
        start = cycle.run_date or cycle.write_date or cycle.create_date
        if not start:
            return 'ok'

        for alert in cls.get_matching_alerts(cycle):
            if alert.type == 'time' and alert.time is not None:
                delta = datetime.timedelta(minutes=alert.time)
                if now >= start + delta:
                    states.append(alert.state)
        if 'danger' in states:
            return 'danger'
        if 'warning' in states:
            return 'warning'
        if 'ok' in states:
            return 'ok'
        return 'ok'

    @classmethod
    def update_alert_state(cls, cycles):
        now = datetime.datetime.now()
        to_save = []
        for cycle in cycles:
            state = cls.compute_alert_state(cycle, now=now)
            if cycle.alert_state != state:
                cycle.alert_state = state
                to_save.append(cycle)
        if to_save:
            cls.save(to_save)

    @classmethod
    def update_alert_state_cron(cls):
        cycles = cls.search([
                ('state', '=', 'running'),
                ])
        cls.update_alert_state(cycles)

    @classmethod
    def view_attributes(cls):
        return super().view_attributes() + [
            ('/tree', 'visual',
                If(Eval('alert_state') == 'danger', 'danger',
                    If(Eval('alert_state') == 'warning', 'warning', '')),
                ['alert_state']),
            ]


class Cron(metaclass=PoolMeta):
    __name__ = 'ir.cron'

    @classmethod
    def __setup__(cls):
        super().__setup__()
        cls.method.selection.extend([
                ('production.work.cycle|update_alert_state_cron',
                    'Update Work Cycle Alert State'),
                ])
