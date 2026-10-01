"""Small arithmetic language for template geometry; never executes Python code."""
import ast
import math
import operator

from .domain import ValidationError

VARIABLES={'native.'+key for key in ('x','y','width','height','size')} | {
    'card.titleLength','card.rulesLength','card.colorCount','card.legendary','card.hasPT'}
OPERATORS={ast.Add:operator.add,ast.Sub:operator.sub,ast.Mult:operator.mul,ast.Div:operator.truediv}
FUNCTIONS={'min':min,'max':max,'clamp':lambda value,low,high:max(low,min(high,value))}


def parse_formula(expression):
    if not isinstance(expression,str) or not expression.strip() or len(expression)>512:
        raise ValidationError('Geometry formulas must be 1–512 characters.')
    try:tree=ast.parse(expression,mode='eval')
    except SyntaxError as exc:raise ValidationError('Invalid geometry formula syntax.') from exc
    if len(list(ast.walk(tree)))>64:raise ValidationError('Geometry formula is too complex.')
    def inspect(node):
        if isinstance(node,ast.Constant) and type(node.value) in {int,float} and abs(node.value)<=10**9 and math.isfinite(node.value):return
        if isinstance(node,ast.Attribute) and isinstance(node.value,ast.Name) and node.value.id+'.'+node.attr in VARIABLES:return
        if isinstance(node,ast.UnaryOp) and isinstance(node.op,(ast.UAdd,ast.USub)):inspect(node.operand);return
        if isinstance(node,ast.BinOp) and type(node.op) in OPERATORS:inspect(node.left);inspect(node.right);return
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id in FUNCTIONS and not node.keywords:
            if not 1<=len(node.args)<=8 or (node.func.id=='clamp' and len(node.args)!=3):
                raise ValidationError('Use clamp(value, minimum, maximum), or min/max with 1–8 values.')
            for argument in node.args:inspect(argument)
            return
        raise ValidationError('Formulas support native/card variables, arithmetic, min, max and clamp only.')
    inspect(tree.body)
    return tree.body


def evaluate_formula(expression,variables):
    def evaluate(node):
        if isinstance(node,ast.Constant):return node.value
        if isinstance(node,ast.Attribute):return variables[node.value.id+'.'+node.attr]
        if isinstance(node,ast.UnaryOp):return -evaluate(node.operand) if isinstance(node.op,ast.USub) else evaluate(node.operand)
        if isinstance(node,ast.BinOp):return OPERATORS[type(node.op)](evaluate(node.left),evaluate(node.right))
        arguments=[evaluate(argument) for argument in node.args]
        if node.func.id in {'min','max'}:return FUNCTIONS[node.func.id](arguments)
        return FUNCTIONS[node.func.id](*arguments)
    try:value=evaluate(parse_formula(expression))
    except (ZeroDivisionError,OverflowError,KeyError) as exc:raise ValidationError('Geometry formula could not be evaluated for this card.') from exc
    if not math.isfinite(value):raise ValidationError('Geometry formula produced a nonfinite number.')
    return value