import pytest
import pysfnc as C
import ast


def stmt_value(txt):
    return ast.parse(txt).body[0]


def expr_value(txt):
    return stmt_value(txt).value


class TestSupportFunctions:
    def test_psf_attr(self):
        val = expr_value('PSF.hello_world')
        assert C.psf_attr(val) == 'hello_world'

    @pytest.mark.parametrize(
        'text',
        ['99 + 42',
         'something_else.odd',
         'PSF.nested.attribute']
    )
    def test_psf_attr_bad_input(self, text):
        val = expr_value(text)
        with pytest.raises(ValueError):
            C.psf_attr(val)
        assert C.psf_attr(val, raise_if_not=False) is None

    def test_chained_key(self):
        val = expr_value('foo["bar"]["baz"]')
        assert C.chained_key(val) == ['foo', 'bar', 'baz']

    def test_simple_chained_key(self):
        val = expr_value('foo')
        assert C.chained_key(val) == ['foo']

    @pytest.mark.parametrize(
        'text',
        ['1 + 1',
         'some_dict[3]["foo"]',
         'some_obj[slice_lb:slice_ub]',
         'some_obj.attrib_access']
    )
    def test_chained_key_bad_input(self, text):
        val = expr_value(text)
        with pytest.raises(ValueError):
            C.chained_key(val)

    def test_chained_key_smr(self):
        assert C.chained_key_smr(['foo']) == '$.locals.foo'
        assert C.chained_key_smr(['foo', 'bar']) == '$.locals.foo.bar'

    def test_maybe_with_next(self):
        assert (C.maybe_with_next({'foo': 99}, None)
                == {'foo': 99})
        assert (C.maybe_with_next({'foo': 99}, 'done')
                == {'foo': 99, 'Next': 'done'})


def _test_factory_raises(nd, cls):
    with pytest.raises(ValueError):
        cls.from_ast_node(nd)


class TestChoice:
    @pytest.fixture(scope='module', params=[C.TestComparison, C.ChoiceCondition])
    def cmp_class(self, request):
        return request.param

    @pytest.fixture(scope='module', params=[C.TestCombinator, C.ChoiceCondition])
    def comb_class(self, request):
        return request.param

    @staticmethod
    def _test_comparison(cmp_class, text, name, variable, literal):
        val = expr_value(text)
        cmp = cmp_class.from_ast_node(val)
        assert cmp.predicate_name == name
        assert cmp.predicate_variable == variable
        assert cmp.predicate_literal == literal

    def test_comparison(self, cmp_class):
        self._test_comparison(cmp_class,
                              'PSF.StringEquals(foo, "bar")',
                              'StringEquals', ['foo'], 'bar')

    def test_chained_comparison(self, cmp_class):
        self._test_comparison(cmp_class,
                              'PSF.StringEquals(foo["bar"], "baz")',
                              'StringEquals', ['foo', 'bar'], 'baz')

    @pytest.mark.parametrize(
        'text',
        ['1 == 1', 'random_check(a, b)']
    )
    def test_comparison_bad_input(self, cmp_class, text):
        _test_factory_raises(expr_value(text), cmp_class)

    @pytest.mark.parametrize(
        'op, exp_opname',
        [('or', 'Or'), ('and', 'And')]
    )
    def test_combinator(self, comb_class, op, exp_opname):
        val = expr_value(f'PSF.StringEquals(foo, "x")'
                         f' {op} PSF.StringEquals(foo["bar"], "y")')
        choice = comb_class.from_ast_node(val)
        assert choice.opname == exp_opname
        assert choice.values[0].predicate_name == 'StringEquals'
        assert choice.values[0].predicate_variable == ['foo']
        assert choice.values[0].predicate_literal == 'x'
        assert choice.values[1].predicate_name == 'StringEquals'
        assert choice.values[1].predicate_variable == ['foo', 'bar']
        assert choice.values[1].predicate_literal == 'y'

    @pytest.mark.parametrize(
        'text',
        ['1 == 1', 'random_check(a, b)', 'x < 77']
    )
    def test_combinator_bad_input(self, comb_class, text):
        _test_factory_raises(expr_value(text), comb_class)

    def test_comparison_conversion_to_smr(self):
        val = expr_value('PSF.StringEquals(foo, "x")')
        choice = C.ChoiceCondition.from_ast_node(val)
        smr = choice.as_choice_rule_smr('wash_dishes')
        assert smr == {'Variable': '$.locals.foo',
                       'StringEquals': 'x',
                       'Next': 'wash_dishes'}

    def test_combinator_conversion_to_smr(self):
        val = expr_value('PSF.StringEquals(foo, "x")'
                         ' or PSF.StringEquals(foo["bar"], "y")')
        choice = C.ChoiceCondition.from_ast_node(val)
        smr = choice.as_choice_rule_smr('wash_dishes')
        assert smr == {'Or': [{'Variable': '$.locals.foo',
                               'StringEquals': 'x'},
                              {'Variable': '$.locals.foo.bar',
                               'StringEquals': 'y'}],
                       'Next': 'wash_dishes'}


class TestRetrySpec:
    def test_retry_spec(self):
        expr = expr_value('(["BadThing", "WorseThing"], 2.5, 3, 2.0)')
        ir = C.RetrySpecIR.from_ast_node(expr)
        assert ir.error_equals == ['BadThing', 'WorseThing']
        assert ir.interval_seconds == 2.5
        assert ir.max_attempts == 3
        assert ir.backoff_rate == 2.0


class TestAstNodeIRs:
    def test_return(self):
        stmt = stmt_value('return banana')
        ir = C.ReturnIR.from_ast_node(stmt)
        assert ir.varname == 'banana'

    def test_return_bad_input(self):
        _test_factory_raises(stmt_value('return 42'), C.ReturnIR)

    def test_raise(self):
        stmt = stmt_value('raise PSF.Fail("OverTemp", "too hot!")')
        ir = C.RaiseIR.from_ast_node(stmt)
        assert ir.error == 'OverTemp'
        assert ir.cause == 'too hot!'

    def test_raise_bad_input(self):
        _test_factory_raises(stmt_value('raise x.y()'), C.RaiseIR)
