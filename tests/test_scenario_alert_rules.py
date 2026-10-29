import datetime
import unittest
from decimal import Decimal

from proteus import Model
from trytond.modules.company.tests.tools import create_company
from trytond.pool import Pool
from trytond.tests.test_tryton import drop_db
from trytond.tests.tools import activate_modules
from trytond.transaction import Transaction


class TestAlertRules(unittest.TestCase):

    def setUp(self):
        drop_db()
        super().setUp()

    def tearDown(self):
        drop_db()
        super().tearDown()

    def test(self):
        config = activate_modules('production_operation_alert', create_company)
        Alert = Model.get('production.operation.alert')
        Center = Model.get('production.work.center')
        Category = Model.get('production.work.center.category')
        Operation = Model.get('production.routing.operation')
        Template = Model.get('product.template')
        Product = Model.get('product.product')
        Uom = Model.get('product.uom')
        Field = Model.get('ir.model.field')
        category = Category(name='Lines', is_line=True)
        category.save()
        lines = []
        centers = []
        products = []
        unit, = Uom.find([('name', '=', 'Unit')])
        for i in range(3):
            line = Center(name=f'Line {i}', category=category)
            line.save()
            center = Center(name=f'Center {i}', parent=line)
            center.save()
            template = Template(name=f'Product {i}', default_uom=unit,
                type='goods', list_price=Decimal(10 + i))
            template.save()
            lines.append(line)
            centers.append(center)
            products.append(Product(template.products[0].id))
        operation = Operation(name='Baking')
        operation.save()
        alert = Alert(name='Baking warning', operation=operation, time=5)
        alert.lines.extend(lines[:2])
        alert.work_centers.extend(centers[:2])
        alert.products.extend(products[:2])
        alert.save()
        alert.reload()
        self.assertEqual(len(alert.lines), 2)
        self.assertEqual(len(alert.work_centers), 2)
        self.assertEqual(len(alert.products), 2)
        time_field, = Field.find([
                ('model', '=', 'product.template'),
                ('name', '=', 'list_price')])
        danger = Alert(name='Product threshold', operation=operation,
            time_field=time_field, state='danger')
        danger.save()

        # A standard text field exercises the same path as custom H:MM fields.
        text_field, = Field.find([
                ('model', '=', 'product.template'), ('name', '=', 'name')])
        text_alert = Alert(name='Text duration', operation=operation,
            time_field=text_field, state='danger')
        text_alert.save()

        with Transaction().start(config.database_name, config.user,
                context=config.context):
            pool = Pool()
            Rule = pool.get('production.operation.alert')
            Production = pool.get('production')
            Work = pool.get('production.work')
            Cycle = pool.get('production.work.cycle')
            Product = pool.get('product.product')
            now = datetime.datetime(2026, 1, 1, 12)
            for index in range(3):
                production = Production(company=config.context['company'],
                    product=products[index].id,
                    line=lines[index].id, work_center=lines[index].id)
                work = Work(production=production,
                    work_center=centers[index].id, operation=operation.id)
                cycle = Cycle(work=work, state='running',
                    run_date=now - datetime.timedelta(minutes=5))
                expected = {danger.id, text_alert.id}
                if index < 2:
                    expected.add(alert.id)
                self.assertEqual(set(work.get_alerts('alerts')), expected)
                self.assertEqual(
                    {a.id for a in Cycle.get_matching_alerts(cycle)}, expected)
                self.assertEqual(Cycle.compute_alert_state(cycle, now),
                    'warning' if index < 2 else 'ok')
                cycle.run_date = now - datetime.timedelta(minutes=10 + index)
                self.assertEqual(Cycle.compute_alert_state(cycle, now), 'danger')
                cycle.state = 'done'
                self.assertEqual(Cycle.compute_alert_state(cycle, now), 'ok')
            production = Production(company=config.context['company'],
                product=products[0].id,
                line=lines[0].id, work_center=lines[0].id)
            work = Work(production=production, work_center=centers[0].id,
                operation=operation.id)
            for record, field, excluded, included in [
                    (production, 'line', lines[2].id, lines[0].id),
                    (production, 'product', products[2].id, products[0].id),
                    (work, 'work_center', centers[2].id, centers[0].id)]:
                setattr(record, field, excluded)
                self.assertEqual(set(work.get_alerts('alerts')),
                    {danger.id, text_alert.id})
                setattr(record, field, included)
            cycle = Cycle(work=work, state='running', run_date=now)
            self.assertEqual(Cycle.compute_alert_state(cycle, now), 'ok')
            ModelRecord = pool.get('ir.model')
            ModelField = pool.get('ir.model.field')
            production_model, = ModelRecord.search([
                    ('name', '=', 'production')])
            date_field, = ModelField.search([
                    ('model', '=', 'production'), ('name', '=', 'planned_date')])
            rule = Rule(alert.id)
            rule.model = production_model
            rule.field = date_field
            production.planned_date = now.date()
            self.assertEqual(Cycle.get_alert_start(cycle, rule),
                datetime.datetime(2026, 1, 1))
            product = Product(products[0].id)
            product.template.list_price = None
            self.assertIsNone(Rule(danger.id).get_time_delta(product))
            product.template.list_price = Decimal(-1)
            self.assertIsNone(Rule(danger.id).get_time_delta(product))
            product.template.list_price = Decimal('0.5')
            self.assertEqual(Rule(danger.id).get_time_delta(product),
                datetime.timedelta(seconds=30))
            product.template.list_price = Decimal(0)
            self.assertEqual(Rule(danger.id).get_time_delta(product),
                datetime.timedelta())

            text_rule = Rule(text_alert.id)
            for value, expected in [
                    ('1:30', 90), ('0:05', 5), (' 2:00 ', 120),
                    ('90', 90), ('0.5', 0.5), ('1,5', 1.5), ('0:00', 0)]:
                product.template.name = value
                self.assertEqual(text_rule.get_time_delta(product),
                    datetime.timedelta(minutes=expected))
            for value in ['', 'invalid', '-1', '-1:30', '1:99',
                    '0:50-0:60', 'nan', 'inf', '1:30:00', '9' * 400]:
                product.template.name = value
                self.assertIsNone(text_rule.get_time_delta(product))
            production.product.template.name = '1:30'
            cycle.run_date = now - datetime.timedelta(minutes=90)
            self.assertEqual(Cycle.compute_alert_state(cycle, now), 'danger')

            # Warning ten minutes before, danger five minutes after 90 minutes.
            Rule.delete([Rule(text_alert.id)])
            Rule.write([Rule(alert.id)], {
                    'time_field': None, 'time': 90,
                    'offset_minutes': 10, 'offset_direction': 'before',
                    })
            Rule.write([Rule(danger.id)], {
                    'time_field': None, 'time': 90,
                    'offset_minutes': 5, 'offset_direction': 'after',
                    })
            cycle.run_date = now
            for minutes, state in [
                    (79, 'ok'), (80, 'warning'), (90, 'warning'),
                    (94, 'warning'), (95, 'danger'), (100, 'danger')]:
                self.assertEqual(Cycle.compute_alert_state(cycle,
                        now + datetime.timedelta(minutes=minutes)), state)
            # The same margins also apply to a product's H:MM field.
            pool.get('product.template').write(
                [production.product.template], {'name': '1:30'})
            Rule.write([Rule(alert.id), Rule(danger.id)], {
                    'time_field': text_field.id, 'time': None,
                    })
            for minutes, state in [
                    (79, 'ok'), (80, 'warning'), (94, 'warning'),
                    (95, 'danger')]:
                self.assertEqual(Cycle.compute_alert_state(cycle,
                        now + datetime.timedelta(minutes=minutes)), state)
            pool.get('product.template').write(
                [production.product.template], {'name': 'No duration'})
            self.assertEqual(Cycle.compute_alert_state(cycle,
                    now + datetime.timedelta(hours=3)), 'ok')
