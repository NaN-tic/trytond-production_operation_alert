# This file is part production_operation_alert module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
import datetime
import re

from trytond.model import ModelSQL, ModelView, fields
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Bool, Eval, If


class OperationAlert(ModelSQL, ModelView):
    'Operation Alert'
    __name__ = 'production.operation.alert'

    name = fields.Char('Name', required=True, translate=True)
    lines = fields.Many2Many(
        'production.operation.alert-line', 'alert', 'line', 'Lines',
        domain=[('category.is_line', '=', True)],
        help='Leave empty to apply to all lines.')
    work_centers = fields.Many2Many(
        'production.operation.alert-work.center', 'alert', 'work_center',
        'Work Centers',
        help='Leave empty to apply to all work centers.')
    products = fields.Many2Many(
        'production.operation.alert-product.product', 'alert', 'product',
        'Products', help='Leave empty to apply to all products.')
    operation = fields.Many2One(
        'production.routing.operation', 'Operation', required=True,
        ondelete='RESTRICT')
    model = fields.Many2One(
        'ir.model', 'Model', domain=[
            ('name', 'in', [
                    'production.work.cycle',
                    'production.work',
                    'production',
                    ]),
            ],
        ondelete='RESTRICT',
        help='Model used to get the date field for the alert calculation.')
    field = fields.Many2One(
        'ir.model.field', 'Field', domain=[
            ('model_ref', '=', Eval('model', -1)),
            ('ttype', 'in', ['date', 'datetime']),
            ],
        depends=['model'],
        ondelete='RESTRICT',
        help=('Date or datetime field used as the start for the alert '
            'calculation.'))
    type = fields.Selection([
            ('time', 'Time'),
            ], 'Type', required=True, sort=False)
    time = fields.Integer(
        'Time', states={
            'required': (Eval('type') == 'time') & ~Eval('time_field'),
            'invisible': (Eval('type') != 'time') | Bool(Eval('time_field')),
            },
        depends=['type', 'time_field'],
        help='Time in minutes before the alert is triggered.')
    time_field = fields.Many2One(
        'ir.model.field', 'Product Time Field',
        domain=[
            ('model', 'in', ['product.product', 'product.template']),
            ('ttype', 'in', [
                    'integer', 'float', 'numeric', 'timedelta', 'char', 'text']),
            ],
        ondelete='RESTRICT',
        help=('Use this product field instead of the fixed time. Numeric '
            'values are minutes; duration fields use their own duration. '
            'Text accepts H:MM or minutes. An empty, invalid or negative '
            'value does not trigger an alert.'))
    offset_minutes = fields.Integer(
        'Margin (minutes)', required=True,
        domain=[('offset_minutes', '>=', 0)],
        help='Minutes before or after the configured time to trigger the alert.')
    offset_direction = fields.Selection([
            ('before', 'Before'),
            ('after', 'After'),
            ], 'When', required=True, sort=False)
    state = fields.Selection([
            ('ok', 'OK'),
            ('warning', 'Warning'),
            ('danger', 'Danger'),
            ], 'State', required=True, sort=False,
        help='State to set on the work cycle when this alert is triggered.')

    @classmethod
    def __register__(cls, module_name):
        super().__register__(module_name)
        table = cls.__table_handler__(module_name)
        # Removed selectors must not prevent inserting the new rules.
        for column in ('line', 'work_center', 'product'):
            if table.column_exist(column):
                table.not_null_action(column, action='remove')

    @staticmethod
    def default_offset_minutes():
        return 0

    @staticmethod
    def default_offset_direction():
        return 'after'

    @staticmethod
    def default_type():
        return 'time'

    @staticmethod
    def default_state():
        return 'warning'

    @fields.depends('model', 'field')
    def on_change_model(self):
        if self.field and self.field.model_ref != self.model:
            self.field = None

    @classmethod
    def get_matching_alerts(cls, work):
        if not work or not work.production or not work.operation:
            return []
        production = work.production
        line = production.line or production.work_center
        domain = [('operation', '=', work.operation.id)]
        for name, record in [
                ('lines', line),
                ('work_centers', work.work_center),
                ('products', production.product)]:
            domain.append(['OR', (name, '=', None),
                    (name, '=', record.id if record else None)])
        return cls.search(domain)

    def get_time_delta(self, product):
        value = self.time
        if self.time_field:
            if not product:
                return None
            record = (product.template
                if self.time_field.model == 'product.template' else product)
            value = getattr(record, self.time_field.name, None)
        if value is None:
            return None
        if isinstance(value, str):
            value = value.strip()
            if ':' in value:
                if not re.fullmatch(r'[0-9]+:[0-5][0-9]', value):
                    return None
                hours, minutes = value.split(':')
                value = int(hours) * 60 + int(minutes)
            else:
                if not re.fullmatch(r'[0-9]+(?:[.,][0-9]+)?', value):
                    return None
                value = value.replace(',', '.')
        if not isinstance(value, datetime.timedelta):
            try:
                value = datetime.timedelta(minutes=float(value))
            except (ValueError, OverflowError):
                return None
        if value < datetime.timedelta():
            return None
        offset = datetime.timedelta(minutes=self.offset_minutes or 0)
        if self.offset_direction == 'before':
            return value - offset
        return value + offset


class OperationAlertLine(ModelSQL):
    'Operation Alert - Line'
    __name__ = 'production.operation.alert-line'

    alert = fields.Many2One(
        'production.operation.alert', 'Alert', required=True,
        ondelete='CASCADE')
    line = fields.Many2One(
        'production.work.center', 'Line', required=True, ondelete='CASCADE')


class OperationAlertWorkCenter(ModelSQL):
    'Operation Alert - Work Center'
    __name__ = 'production.operation.alert-work.center'

    alert = fields.Many2One(
        'production.operation.alert', 'Alert', required=True,
        ondelete='CASCADE')
    work_center = fields.Many2One(
        'production.work.center', 'Work Center', required=True,
        ondelete='CASCADE')


class OperationAlertProduct(ModelSQL):
    'Operation Alert - Product'
    __name__ = 'production.operation.alert-product.product'

    alert = fields.Many2One(
        'production.operation.alert', 'Alert', required=True,
        ondelete='CASCADE')
    product = fields.Many2One(
        'product.product', 'Product', required=True, ondelete='CASCADE')


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
        'get_alerts', setter='set_alerts')

    def get_alerts(self, name):
        Alert = Pool().get('production.operation.alert')

        return [a.id for a in Alert.get_matching_alerts(self)]

    @classmethod
    def set_alerts(cls, works, name, value):
        pass

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

        return Alert.get_matching_alerts(cycle.work)

    @classmethod
    def get_alert_record(cls, cycle, alert):
        if not alert.model:
            return cycle
        model_name = alert.model.name
        if model_name == 'production.work.cycle':
            return cycle
        if model_name == 'production.work':
            return cycle.work
        if model_name == 'production':
            return cycle.work.production if cycle.work else None
        return None

    @classmethod
    def get_alert_start(cls, cycle, alert):
        if alert.field:
            record = cls.get_alert_record(cycle, alert)
            if record:
                value = getattr(record, alert.field.name, None)
                if value:
                    if isinstance(value, datetime.date) and not isinstance(
                            value, datetime.datetime):
                        return datetime.datetime.combine(
                            value, datetime.time.min)
                    return value
        return cycle.run_date or cycle.write_date or cycle.create_date

    @classmethod
    def compute_alert_state(cls, cycle, now=None):
        if now is None:
            now = datetime.datetime.now()
        if cycle.state != 'running':
            return 'ok'

        states = []
        for alert in cls.get_matching_alerts(cycle):
            start = cls.get_alert_start(cycle, alert)
            if not start:
                continue
            if alert.type == 'time':
                delta = alert.get_time_delta(cycle.work.production.product)
                if delta is not None and now >= start + delta:
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
