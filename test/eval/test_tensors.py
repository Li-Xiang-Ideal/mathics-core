# -*- coding: utf-8 -*-
"""
Unit tests for mathics.eval.tensors
"""
import unittest

from mathics.core.definitions import Definitions
from mathics.core.evaluation import Evaluation
from mathics.core.expression import Expression
from mathics.eval.tensors import unpack_outer


class UnpackOuterTest(unittest.TestCase):
    def setUp(self):
        definitions = Definitions(add_builtin=True)
        self.evaluation = Evaluation(definitions, catch_interrupt=False)

    def testTuples(self):
        """
        Tuples can be implemented by unpack_outer.
        """
        list1 = [1, 2, 3]
        list2 = [4, 5]
        list3 = [6, 7, 8]

        expected_result = [
            [[(1, 4, 6), (1, 4, 7), (1, 4, 8)], [(1, 5, 6), (1, 5, 7), (1, 5, 8)]],
            [[(2, 4, 6), (2, 4, 7), (2, 4, 8)], [(2, 5, 6), (2, 5, 7), (2, 5, 8)]],
            [[(3, 4, 6), (3, 4, 7), (3, 4, 8)], [(3, 5, 6), (3, 5, 7), (3, 5, 8)]],
        ]  # Tuples[{list1, list2, list3}]

        etc_1 = (
            lambda item, level: level > 1,
            # True to unpack the next list, False to unpack the current list at the next level
            lambda item: item,
            # get elements from Expression, for iteratable objects (tuple, list, etc.) it's just identity
            list,
            # apply_head: each level of result would be in form of apply_head(...)
            tuple,
            # apply_f: lowest level of result would be apply_f(joined lowest level elements of each list)
            lambda current, item: current + [item],
            # join current lowest level elements (i.e. current) with a new one, in most cases it's just "Append"
            False,
            # True for result as flattened list like {a,b,c,d}, False for result as nested list like {{a,b},{c,d}}
            self.evaluation,  # evaluation
        )

        etc_2 = (
            lambda item, level: not isinstance(item, list),
            # list1~list3 all have depth 1, so level > 1 equals to not isinstance(item, list)
            lambda item: item,
            lambda elements: elements,
            # internal level structure used in unpack_outer is exactly list, so list equals to identity
            lambda current: current,
            # now join_elem is in form of tuple, so we no longer need to convert it to tuple
            lambda current, item: current + (item,),
            False,
            self.evaluation,
        )

        assert unpack_outer(list1, [list2, list3], [], 1, etc_1) == expected_result
        assert unpack_outer(list1, [list2, list3], (), 1, etc_2) == expected_result


if __name__ == "__main__":
    unittest.main()
