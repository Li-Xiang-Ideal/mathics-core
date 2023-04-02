# -*- coding: utf-8 -*-
"""
Precedence-climbing Parsing routines for grammar symbols.

See README.md or
https://mathics-development-guide.readthedocs.io/en/latest/extending/code-overview/scanning-and-parsing.html#parser
"""


import string
from typing import Optional, Union

from mathics_scanner import (
    InvalidSyntaxError,
    Tokeniser,
    TranslateError,
    is_symbol_name,
)
from mathics_scanner.tokeniser import Token

from mathics.core.parser.ast import (
    Filename,
    Node,
    NullString,
    NullSymbol,
    Number,
    Number1,
    NumberM1,
    String,
    Symbol,
)
from mathics.core.parser.operators import (
    all_ops,
    binary_ops,
    flat_binary_ops,
    inequality_ops,
    left_binary_ops,
    misc_ops,
    nonassoc_binary_ops,
    postfix_ops,
    prefix_ops,
    right_binary_ops,
    ternary_ops,
)

special_symbols = {
    "\u03C0": "Pi",  # Pi
    "\uF74D": "E",  # ExponentialE
    "\uF74E": "I",  # ImaginaryI
    "\uF74F": "I",  # ImaginaryJ
    "\u221E": "Infinity",  # Infinity
    "\u00B0": "Degree",  # Degree
}


permitted_digits = {c: i for i, c in enumerate(string.digits + string.ascii_lowercase)}
permitted_digits["."] = 0


class Parser:
    def __init__(self):
        # no implicit times on these tokens
        self.halt_tags = set(
            [
                "END",
                "RawRightAssociation",
                "RawRightParenthesis",
                "RawComma",
                "RawRightBrace",
                "RawRightBracket",
                "RawColon",
                "DifferentialD",
            ]
        )

    def parse(self, feeder):
        self.feeder = feeder
        self.tokeniser = Tokeniser(feeder)
        self.current_token = None
        self.bracket_depth = 0
        self.box_depth = 0
        return self.parse_e()

    def next(self):
        if self.current_token is None:
            self.current_token = self.tokeniser.next()
        return self.current_token

    def next_noend(self):
        "returns next token which is not END"
        while True:
            token = self.next()
            if token.tag != "END":
                return token
            self.incomplete(token.pos)

    def consume(self):
        self.current_token = None

    def incomplete(self, pos):
        self.tokeniser.incomplete()
        self.backtrack(pos)

    def expect(self, expected_tag):
        token = self.next_noend()
        if token.tag == expected_tag:
            self.consume()
        else:
            self.tokeniser.sntx_message(token.pos)
            raise InvalidSyntaxError()

    def backtrack(self, pos):
        self.tokeniser.pos = pos
        self.current_token = None

    def parse_e(self) -> Union[Node, Optional[list]]:
        result = []
        while self.next().tag != "END":
            result.append(self.parse_exp(0))
        if len(result) > 1:
            return Node("Times", *result)
        if len(result) == 1:
            return result[0]
        else:
            return None

    def parse_exp(self, p: int):
        result = self.parse_p()
        while True:
            if self.bracket_depth > 0:
                token = self.next_noend()
            else:
                token = self.next()
            tag = token.tag
            method = getattr(self, "e_" + tag, None)
            if method is not None:
                new_result = method(result, token, p)
            elif tag in inequality_ops:
                new_result = self.parse_inequality(result, token, p)
            elif tag in binary_ops:
                new_result = self.parse_binary(result, token, p)
            elif tag in ternary_ops:
                new_result = self.parse_ternary(result, token, p)
            elif tag in postfix_ops:
                new_result = self.parse_postfix(result, token, p)
            elif tag not in self.halt_tags and flat_binary_ops["Times"] >= p:
                # implicit times
                q = flat_binary_ops["Times"]
                child = self.parse_exp(q + 1)
                new_result = Node("Times", result, child).flatten()
            else:
                new_result = None
            if new_result is None:
                break
            else:
                result = new_result
        return result

    def parse_p(self):
        token = self.next_noend()
        tag = token.tag
        method = getattr(self, "p_" + tag, None)
        if method is not None:
            return method(token)
        elif tag in prefix_ops:
            self.consume()
            q = prefix_ops[tag]
            child = self.parse_exp(q)
            return Node(tag, child)
        else:
            self.tokeniser.sntx_message(token.pos)
            raise InvalidSyntaxError()

    def parse_box(self, p):
        result = None
        while True:
            token = self.next()
            tag = token.tag
            method = getattr(self, "b_" + tag, None)
            if method is not None:
                new_result = method(result, token, p)
            elif tag in ("OtherscriptBox", "RightRowBox"):
                break
            elif tag == "END":
                self.incomplete(token.pos)
            elif result is None and tag != "END":
                self.consume()
                new_result = String(token.text)
                if new_result.value == r"\(":
                    new_result = self.p_LeftRowBox(token)
            else:
                new_result = None
            if new_result is None:
                break
            else:
                result = new_result
        if result is None:
            result = NullString
        return result

    def parse_seq(self) -> list:
        result = []
        while True:
            token = self.next_noend()
            tag = token.tag
            if tag == "RawComma":
                self.tokeniser.feeder.message("Syntax", "com")
                result.append(NullSymbol)
                self.consume()
            elif tag in ("RawRightAssociation", "RawRightBrace", "RawRightBracket"):
                if result:
                    self.tokeniser.feeder.message("Syntax", "com")
                    result.append(NullSymbol)
                break
            else:
                result.append(self.parse_exp(0))
                token = self.next_noend()
                tag = token.tag
                if tag == "RawComma":
                    self.consume()
                    continue
                elif tag in ("RawRightAssociation", "RawRightBrace", "RawRightBracket"):
                    break
        return result

    def parse_inequality(self, expr1, token: Token, p: int) -> Optional[Node]:
        tag = token.tag
        q = flat_binary_ops[tag]
        if q < p:
            return None
        self.consume()
        head = expr1.get_head_name()
        expr2 = self.parse_exp(q + 1)
        if head == "Inequality" and not expr1.parenthesised:
            expr1.children.append(Symbol(tag))
            expr1.children.append(expr2)
        elif head in inequality_ops and head != tag and not expr1.parenthesised:
            children = []
            first = True
            for child in expr1.children:
                if not first:
                    children.append(Symbol(head))
                children.append(child)
                first = False
            children.append(Symbol(tag))
            children.append(expr2)
            expr1 = Node("Inequality", *children)
        else:
            expr1 = Node(tag, expr1, expr2).flatten()
        return expr1

    def parse_binary(self, expr1, token: Token, p: int) -> Optional[Node]:
        tag = token.tag
        q = binary_ops[tag]
        if q < p:
            return None
        self.consume()
        if tag not in right_binary_ops:
            q += 1
        expr2 = self.parse_exp(q)
        # flatten or associate
        if (
            tag in nonassoc_binary_ops
            and expr1.get_head_name() == tag
            and not expr1.parenthesised
        ):
            self.tokeniser.sntx_message(token.pos)
            raise InvalidSyntaxError()
        result = Node(tag, expr1, expr2)
        if tag in flat_binary_ops:
            result.flatten()
        return result

    def parse_postfix(self, expr1, token: Token, p: int) -> Optional[Node]:
        tag = token.tag
        q = postfix_ops[tag]
        if q < p:
            return None
        self.consume()
        return Node(tag, expr1)

    def parse_ternary(self, expr1, token: Token, p: int) -> Optional[Node]:
        raise NotImplementedError

    # P methods
    #
    # p_xxx methods are called from parse_p.
    # Called with one Token and return a Node.
    # Used for prefix operators and brackets.

    def p_Factorial(self, token):
        self.consume()
        q = prefix_ops["Not"]
        child = self.parse_exp(q)
        return Node("Not", child)

    def p_Factorial2(self, token):
        self.consume()
        q = prefix_ops["Not"]
        child = self.parse_exp(q)
        return Node("Not", Node("Not", child))

    def p_RawLeftParenthesis(self, token):
        self.consume()
        self.bracket_depth += 1
        result = self.parse_exp(0)
        self.expect("RawRightParenthesis")
        self.bracket_depth -= 1
        result.parenthesised = True
        return result

    def p_RawLeftBrace(self, token) -> Node:
        self.consume()
        self.bracket_depth += 1
        seq = self.parse_seq()
        self.expect("RawRightBrace")
        self.bracket_depth -= 1
        return Node("List", *seq)

    def p_RawLeftAssociation(self, token) -> Node:
        self.consume()
        self.bracket_depth += 1
        seq = self.parse_seq()
        self.expect("RawRightAssociation")
        self.bracket_depth -= 1
        return Node("Association", *seq)

    def p_LeftRowBox(self, token) -> Node:
        self.consume()
        children = []
        # If this does not happen, it would be because
        # it was called when a `FormBox` (or any other)
        # was found. More generally, we could use
        # ``token.tag == "LeftRowBox"
        # if there were other Tokens with a
        # similar behaviour (see bellow).

        if token.tag != "FormBox":
            self.box_depth += 1
            self.bracket_depth += 1

        token = self.next()
        while token.tag not in ("RightRowBox", "OtherscriptBox", "FormBox"):
            newnode = self.parse_box(0)
            children.append(newnode)
            token = self.next()

        # FormBox token has a particular behaviour: if it is found inside
        # a RowBox, it splits the Rowbox in two pieces: the part at the
        # left is taken as a "Format" and the part at the right is parsed
        # as the Box to be formatted, in a way that
        # \(a_1, a_2 ... \` b_1 b_2 ... \) is parsed as
        # FormBox[RowBox[{b_1, b_2,...}], RowBox[a_1, a_2, ...]]
        # This kind of parsing is not supported by the standard mechanism,
        # so we need to processing it here instead of using a p_FormBox
        # method.
        # The strategy to deal with is that, when a "FormBox" tag is found,
        # the collected elements are used to build the second argument of the
        # output, and then the method is called again to parse the rest of the
        # box as it had started at the "FormBox" tag. In this new call,
        # neither `self.box_depth` or `self.bracket_depth` are going to be
        # incremented, but are decremented at the end of the child expression.
        if token.tag == "FormBox":
            if len(children) == 0:
                fmt = Symbol("StandardForm")
            elif len(children) == 1:
                fmt = children[0]
                if type(fmt) is String:
                    fmt_name = fmt.value
                    if is_symbol_name(fmt_name):
                        fmt = Symbol(fmt_name)
                    else:
                        fmt = Node("Removed", String("$$Failure"))
            else:
                fmt = Node("RowBox", Node("List", *children))
            rest = self.p_LeftRowBox(token)
            return Node("FormBox", rest, fmt)
        if len(children) == 0:
            result = NullString
        elif len(children) == 1:
            result = children[0]
        else:
            result = Node("RowBox", Node("List", *children))
        self.expect("RightRowBox")
        self.box_depth -= 1
        self.bracket_depth -= 1
        result.parenthesised = True
        return result

    def p_Number(self, token) -> Number:
        s = token.text

        # sign
        if s[0] == "-":
            s = s[1:]
            sign = -1
        else:
            sign = 1

        # base
        s = s.split("^^")
        if len(s) == 1:
            base, s = 10, s[0]
        else:
            assert len(s) == 2
            base, s = int(s[0]), s[1]
            if not 2 <= base <= 36:
                self.tokeniser.feeder.message("General", "base", base, token.text, 36)
                self.tokeniser.sntx_message(token.pos)
                raise InvalidSyntaxError()

        # mantissa
        s = s.split("*^")
        if len(s) == 1:
            exp, s = 0, s[0]
        else:
            # TODO modify regex and provide error if `exp` is not an int
            exp, s = int(s[1]), s[0]

        # precision/accuracy
        s = s.split("`", 1)
        if len(s) == 1:
            s, suffix = s[0], None
        else:
            s, suffix = s[0], s[1]

        for i, c in enumerate(s.lower()):
            if permitted_digits[c] >= base:
                self.tokeniser.feeder.message("General", "digit", i + 1, s, base)
                self.tokeniser.sntx_message(token.pos)
                raise InvalidSyntaxError()

        result = Number(s, sign=sign, base=base, suffix=suffix, exp=exp)
        self.consume()
        return result

    def p_String(self, token) -> String:
        result = String(token.text[1:-1])
        self.consume()
        return result

    def p_Symbol(self, token) -> Symbol:
        symbol_name = special_symbols.get(token.text, token.text)
        result = Symbol(symbol_name, context=None)
        self.consume()
        return result

    def p_Filename(self, token) -> Filename:
        result = Filename(token.text)
        self.consume()
        return result

    def p_Span(self, token):
        return self.e_Span(Number1, token, 0)

    def p_Integral(self, token) -> Node:
        self.consume()
        inner_prec, outer_prec = all_ops["Sum"] + 1, all_ops["Power"] - 1
        expr1 = self.parse_exp(inner_prec)
        self.expect("DifferentialD")
        expr2 = self.parse_exp(outer_prec)
        return Node("Integrate", expr1, expr2)

    def p_Pattern(self, token) -> Node:
        self.consume()
        text = token.text
        if "." in text:
            name = text[:-2]
            if name:
                return Node(
                    "Optional",
                    Node("Pattern", Symbol(name, context=None), Node("Blank")),
                )
            else:
                return Node("Optional", Node("Blank"))
        pieces = text.split("_")
        count = len(pieces) - 1
        if count == 1:
            name = "Blank"
        elif count == 2:
            name = "BlankSequence"
        elif count == 3:
            name = "BlankNullSequence"
        if pieces[-1]:
            blank = Node(name, Symbol(pieces[-1], context=None))
        else:
            blank = Node(name)
        if pieces[0]:
            return Node("Pattern", Symbol(pieces[0], context=None), blank)
        else:
            return blank

    def p_Minus(self, token):
        self.consume()
        q = prefix_ops["Minus"]
        expr = self.parse_exp(q)
        if isinstance(expr, Number) and not expr.value.startswith("-"):
            expr.value = "-" + expr.value
            return expr
        else:
            return Node("Times", NumberM1, expr).flatten()

    def p_Plus(self, token):
        self.consume()
        q = prefix_ops["Minus"]
        # note flattening here even flattens e.g. + a + b
        return Node("Plus", self.parse_exp(q)).flatten()

    def p_PlusMinus(self, token) -> Node:
        self.consume()
        q = prefix_ops["Minus"]
        return Node("PlusMinus", self.parse_exp(q))

    def p_MinusPlus(self, token) -> Node:
        self.consume()
        q = prefix_ops["Minus"]
        return Node("MinusPlus", self.parse_exp(q))

    def p_Out(self, token) -> Node:
        self.consume()
        text = token.text
        if text == "%":
            return Node("Out")
        if text.endswith("%"):
            n = str(-len(text))
        else:
            n = text[1:]
        return Node("Out", Number(n))

    def p_Slot(self, token) -> Node:
        self.consume()
        text = token.text
        if len(text) == 1:
            n = Number1
        else:
            n = text[1:]
            if n.isdigit():
                n = Number(n)
            else:
                n = String(n)
        return Node("Slot", n)

    def p_SlotSequence(self, token) -> Node:
        self.consume()
        text = token.text
        if len(text) == 2:
            n = "1"
        else:
            n = text[2:]
        return Node("SlotSequence", Number(n))

    def p_Increment(self, token) -> Node:
        self.consume()
        q = prefix_ops["PreIncrement"]
        return Node("PreIncrement", self.parse_exp(q))

    def p_Decrement(self, token) -> Node:
        self.consume()
        q = prefix_ops["PreDecrement"]
        return Node("PreDecrement", self.parse_exp(q))

    def p_PatternTest(self, token) -> Node:
        self.consume()
        q = prefix_ops["Definition"]
        child = self.parse_exp(q)
        return Node(
            "Information", child, Node("Rule", Symbol("LongForm"), Symbol("False"))
        )

    def p_Information(self, token) -> Node:
        self.consume()
        q = prefix_ops["Information"]
        child = self.parse_exp(q)
        if child.__class__ is not Symbol:
            raise InvalidSyntaxError()
        return Node(
            "Information", child, Node("Rule", Symbol("LongForm"), Symbol("True"))
        )

    # E methods
    #
    # e_xxx methods are called from parse_e.
    # They expect args (Node, Token precedence) and return Node or None.
    # Used for binary and ternary operators.
    # return None if precedence is too low.

    def e_Span(self, expr1, token, p) -> Optional[Node]:
        q = ternary_ops["Span"]
        if q < p:
            return None

        if expr1.get_head_name() == "Span" and not expr1.parenthesised:
            return None
        self.consume()
        # Span[expr1, expr2]
        token = self.next()
        if token.tag == "Span":
            expr2 = Symbol("All")
        elif token.tag == "END" and self.bracket_depth == 0:
            # So that e.g. 'x = 1 ;;' doesn't wait for newline in the frontend
            expr2 = Symbol("All")
            return Node("Span", expr1, expr2)
        else:
            messages = list(self.feeder.messages)
            try:
                expr2 = self.parse_exp(q + 1)
            except TranslateError:
                expr2 = Symbol("All")
                self.backtrack(token.pos)
                self.feeder.messages = messages
        token = self.next()
        if token.tag == "Span":
            self.consume()
            messages = list(self.feeder.messages)
            try:
                expr3 = self.parse_exp(q + 1)
                return Node("Span", expr1, expr2, expr3)
            except TranslateError:
                self.backtrack(token.pos)
                self.feeder.messages = messages
        return Node("Span", expr1, expr2)

    def e_RawLeftBracket(self, expr, token: Token, p: int) -> Optional[Node]:
        q = all_ops["Part"]
        if q < p:
            return None
        self.consume()
        self.bracket_depth += 1
        token = self.next_noend()
        if token.tag == "RawLeftBracket":
            self.consume()
            seq = self.parse_seq()
            self.expect("RawRightBracket")
            self.expect("RawRightBracket")
            self.bracket_depth -= 1
            return Node("Part", expr, *seq)
        else:
            seq = self.parse_seq()
            self.expect("RawRightBracket")
            self.bracket_depth -= 1
            result = Node(expr, *seq)
            result.parenthesised = True
            return result

    def e_Infix(self, expr1, token, p) -> Optional[Node]:
        q = ternary_ops["Infix"]
        if q < p:
            return None
        self.consume()
        expr2 = self.parse_exp(q + 1)
        self.expect("Infix")
        expr3 = self.parse_exp(q + 1)
        return Node(expr2, expr1, expr3)

    def e_Postfix(self, expr1, token: Token, p: int) -> Optional[Node]:
        q = left_binary_ops["Postfix"]
        if q < p:
            return None
        self.consume()
        # postix has lowest prec and is left assoc
        expr2 = self.parse_exp(q + 1)
        return Node(expr2, expr1)

    def e_Prefix(self, expr1, token: Token, p: int) -> Optional[Node]:
        q = 640
        if 640 < p:
            return None
        self.consume()
        expr2 = self.parse_exp(q)
        return Node(expr1, expr2)

    def e_ApplyList(self, expr1, token: Token, p: int) -> Optional[Node]:
        q = right_binary_ops["Apply"]
        if q < p:
            return None
        self.consume()
        expr2 = self.parse_exp(q)
        expr3 = Node("List", Number1)
        return Node("Apply", expr1, expr2, expr3)

    def e_Function(self, expr1, token: Token, p: int) -> Optional[Node]:
        q = postfix_ops["Function"]
        if q < p:
            return None
        # postfix or right-binary determined by symbol
        self.consume()
        if token.text == "&":
            return Node("Function", expr1)
        else:
            expr2 = self.parse_exp(q)
            return Node("Function", expr1, expr2)

    def e_RawColon(self, expr1, token: Token, p: int) -> Optional[Node]:
        head_name = expr1.get_head_name()
        if head_name == "Symbol":
            head = "Pattern"
        elif head_name in (
            "Blank",
            "BlankSequence",
            "BlankNullSequence",
            "Pattern",
            "Optional",
        ):
            head = "Optional"
        else:
            return None
        q = all_ops[head]
        if p == 151:
            return None
        self.consume()
        expr2 = self.parse_exp(q + 1)
        return Node(head, expr1, expr2)

    def e_Semicolon(self, expr1, token: Token, p: int) -> Optional[Node]:
        q = flat_binary_ops["CompoundExpression"]
        if q < p:
            return None
        self.consume()

        # XXX this has to come before call to self.next()
        pos = self.tokeniser.pos
        messages = list(self.feeder.messages)

        # So that e.g. 'x = 1;' doesn't wait for newline in the frontend
        tag = self.next().tag
        if tag == "END" and self.bracket_depth == 0:
            expr2 = NullSymbol
            return Node("CompoundExpression", expr1, expr2).flatten()

        # XXX look for next expr otherwise backtrack
        try:
            expr2 = self.parse_exp(q + 1)
        except TranslateError:
            self.backtrack(pos)
            self.feeder.messages = messages
            expr2 = NullSymbol
        return Node("CompoundExpression", expr1, expr2).flatten()

    def e_Minus(self, expr1, token: Token, p: int) -> Optional[Node]:
        q = left_binary_ops["Subtract"]
        if q < p:
            return None
        self.consume()
        expr2 = self.parse_exp(q + 1)
        if isinstance(expr2, Number) and not expr2.value.startswith("-"):
            expr2.value = "-" + expr2.value
        else:
            expr2 = Node("Times", NumberM1, expr2).flatten()
        return Node("Plus", expr1, expr2).flatten()

    def e_TagSet(self, expr1, token: Token, p: int) -> Optional[Node]:
        q = all_ops["Set"]
        if q < p:
            return None
        self.consume()
        expr2 = self.parse_exp(q + 1)
        # examine next token
        token = self.next_noend()
        tag = token.tag
        if tag == "Set":
            head = "TagSet"
        elif tag == "SetDelayed":
            head = "TagSetDelayed"
        elif tag == "Unset":
            head = "TagUnset"
        else:
            self.tokeniser.sntx_message(token.pos)
            raise InvalidSyntaxError()
        self.consume()
        if head == "TagUnset":
            return Node(head, expr1, expr2)
        expr3 = self.parse_exp(q + 1)
        return Node(head, expr1, expr2, expr3)

    def e_Unset(self, expr1, token: Token, p: int) -> Optional[Node]:
        q = all_ops["Set"]
        if q < p:
            return None
        self.consume()
        return Node("Unset", expr1)

    def e_Derivative(self, expr1, token: Token, p: int) -> Optional[Node]:
        q = postfix_ops["Derivative"]
        if q < p:
            return None
        n = 0
        while self.next().tag == "Derivative":
            self.consume()
            n += 1
        head = Node("Derivative", Number(str(n)))
        return Node(head, expr1)

    def e_Divide(self, expr1, token: Token, p: int):
        q = left_binary_ops["Divide"]
        if q < p:
            return None
        self.consume()
        expr2 = self.parse_exp(q + 1)
        return Node("Times", expr1, Node("Power", expr2, NumberM1)).flatten()

    def e_Alternatives(self, expr1, token: Token, p: int) -> Optional[Node]:
        q = flat_binary_ops["Alternatives"]
        if q < p:
            return None
        self.consume()
        expr2 = self.parse_exp(q + 1)
        return Node("Alternatives", expr1, expr2).flatten()

    def e_MessageName(self, expr1, token: Token, p: int) -> Node:
        elements = [expr1]
        while self.next().tag == "MessageName":
            self.consume()
            token = self.next()
            if token.tag == "Symbol":
                # silently convert Symbol to String
                self.consume()
                element = String(token.text)
            elif token.tag == "String":
                element = self.p_String(token)
            else:
                self.tokeniser.sntx_message(token.pos)
                raise InvalidSyntaxError()
            elements.append(element)
        return Node("MessageName", *elements)

    # B methods
    #
    # b_xxx methods are called from parse_box.
    # They expect args (Node, Token precedence) and return Node or None.
    # The first argument may be None if the LHS is absent.
    # Used for boxes.

    def b_SqrtBox(self, box0, token: Token, p: int) -> Optional[Node]:
        if box0 is not None:
            return None
        self.consume()
        q = misc_ops["SqrtBox"]
        box1 = self.parse_box(q)
        if self.next().tag == "OtherscriptBox":
            self.consume()
            box2 = self.parse_box(q)
            return Node("RadicalBox", box1, box2)
        else:
            return Node("SqrtBox", box1)

    def b_SuperscriptBox(self, box1, token: Token, p: int) -> Optional[Node]:
        q = misc_ops["SuperscriptBox"]
        if q < p:
            return None
        if box1 is None:
            box1 = NullString
        self.consume()
        box2 = self.parse_box(q)
        if self.next().tag == "OtherscriptBox":
            self.consume()
            box3 = self.parse_box(misc_ops["SubsuperscriptBox"])
            return Node("SubsuperscriptBox", box1, box3, box2)
        else:
            return Node("SuperscriptBox", box1, box2)

    def b_SubscriptBox(self, box1, token: Token, p: int) -> Optional[Node]:
        q = misc_ops["SubscriptBox"]
        if q < p:
            return None
        if box1 is None:
            box1 = NullString
        self.consume()
        box2 = self.parse_box(q)
        if self.next().tag == "OtherscriptBox":
            self.consume()
            box3 = self.parse_box(misc_ops["SubsuperscriptBox"])
            return Node("SubsuperscriptBox", box1, box2, box3)
        else:
            return Node("SubscriptBox", box1, box2)

    def b_UnderscriptBox(self, box1, token: Token, p: int) -> Optional[Node]:
        q = misc_ops["UnderscriptBox"]
        if q < p:
            return None
        if box1 is None:
            box1 = NullString
        self.consume()
        box2 = self.parse_box(q)
        if self.next().tag == "OtherscriptBox":
            self.consume()
            box3 = self.parse_box(misc_ops["UnderoverscriptBox"])
            return Node("UnderoverscriptBox", box1, box2, box3)
        else:
            return Node("UnderscriptBox", box1, box2)

    def b_FractionBox(self, box1, token: Token, p: int) -> Optional[Node]:
        q = misc_ops["FractionBox"]
        if q < p:
            return None
        if box1 is None:
            box1 = NullString
        self.consume()
        box2 = self.parse_box(q + 1)
        return Node("FractionBox", box1, box2)

    def b_FormBox(self, box1, token: Token, p: int) -> Optional[Node]:
        q = misc_ops["FormBox"]
        if q < p:
            return None
        if box1 is None:
            box1 = Symbol("StandardForm")  # RawForm
        elif is_symbol_name(box1.value):
            box1 = Symbol(box1.value, context=None)
        else:
            box1 = Node("Removed", String("$$Failure"))
        self.consume()
        box2 = self.parse_box(q)
        return Node("FormBox", box2, box1)

    def b_OverscriptBox(self, box1, token: Token, p: int) -> Optional[Node]:
        q = misc_ops["OverscriptBox"]
        if q < p:
            return None
        if box1 is None:
            box1 = NullString
        self.consume()
        box2 = self.parse_box(q)
        if self.next().tag == "OtherscriptBox":
            self.consume()
            box3 = self.parse_box(misc_ops["UnderoverscriptBox"])
            return Node("UnderoverscriptBox", box1, box3, box2)
        else:
            return Node("OverscriptBox", box1, box2)
