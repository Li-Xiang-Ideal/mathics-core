# -*- coding: utf-8 -*-
# Internal graphics routines.
# No external builtins appear here.
# Also no docstring which may confuse the doc system


from mathics.builtin.base import (
    InstanceableBuiltin,
    BoxConstruct,
    BoxConstructError,
    split_name,
    expand_builtin_name_for_description,
)

# Signals to Mathics doc processing not to include this module in its documentation.
no_doc = True

from mathics.core.symbols import system_symbols_dict, Symbol


class _GraphicsDirective(InstanceableBuiltin):
    def __new__(cls, *args, **kwargs):
        # This ensures that all the graphics elements have a well formatted docstring
        # and a summary_text
        instance = super().__new__(cls, *args, **kwargs)
        if not hasattr(instance, "summary_text"):
            article = (
                "an "
                if instance.get_name()[0].lower() in ("a", "e", "i", "o", "u")
                else "a "
            )
            instance.summary_text = "graphics directive setting the " + split_name(
                cls.get_name(short=True)
            )
        #            clsname = cls.get_name()
        #            if clsname[0] in ("A", "E", "I", "O", "U"):
        #                instance.summary_text = f"boxes for an '{cls.get_name()}' element"
        #            else:
        #                instance.summary_text = f"boxes for a '{cls.get_name()}' element"
        if not instance.__doc__:
            instance.__doc__ = f"""
                <dl>
                <dt>'{cls.get_name()}[...]'
                <dd>is a graphics directive that sets {cls.get_name().lower()[:-3]}
                </dl>
                """
        return instance

    def init(self, graphics, item=None):
        print("item:", item)
        if item is not None and not item.has_form(self.get_name(), None):
            raise BoxConstructError
        self.graphics = graphics

    @staticmethod
    def create_as_style(klass, graphics, item):
        return klass(graphics, item)


# Check if  _GraphicsElement shouldn't be a BoxConstruct instead of an InstanceableBuiltin
class _GraphicsElementBox(BoxConstruct):
    def __new__(cls, *args, **kwargs):
        # This ensures that all the graphics directive have a well formatted docstring
        # and a summary_text
        instance = super().__new__(cls, *args, **kwargs)
        # In case it is not set, build a default summary_text and
        # a docstring from the name of the class
        undef_summary = not hasattr(instance, "summary_text")
        undef_docstr = not instance.__doc__
        if undef_summary or undef_docstr:
            builtin_name = instance.get_name(short=True)
            short_name = expand_builtin_name_for_description(builtin_name)
            is_box = len(builtin_name) > 3 and builtin_name[-3:] == "Box"
            if undef_summary:
                if is_box:
                    instance.summary_text = f"box representation for {short_name}"
                else:
                    instance.summary_text = f"{short_name} graphics element"
            if undef_docstr:
                if is_box:
                    instance.__doc__ = (
                        "\t<dl>"
                        f"\t<dt>'{builtin_name}[...]'"
                        f"\t\t<dd>is box structure representing a {short_name}."
                        "</dl>"
                    )
                else:
                    instance.__doc__ = (
                        "\t<dl>"
                        f"\t<dt>'{builtin_name}[...]'"
                        f"\t\t<dd>represents {short_name} graphic object."
                        "</dl>"
                    )

        return instance

    def init(self, graphics, item=None):
        if item is not None and not item.has_form(self.get_name(), None):
            raise BoxConstructError
        self.graphics = graphics


#    @staticmethod
#    def create_as_style(klass, graphics, item):
#        return klass(graphics, item)


class _GraphicsElementBox(BoxConstruct):
    def init(self, graphics, item=None, style=None, opacity=1.0):
        if item is not None and not item.has_form(self.get_name(), None):
            raise BoxConstructError
        self.graphics = graphics
        self.style = style
        self.opacity = opacity
        self.is_completely_visible = False  # True for axis elements


def get_class(symbol: Symbol):
    """
    Returns the Builtin graphic primitive associated to the
    Symbol `symbol`
    """
    c = GLOBALS.get(symbol)
    if c is None:
        return GLOBALS3D.get(symbol)
    else:
        return c

    # globals() does not work with Cython, otherwise one could use something
    # like return globals().get(name)


# FIXME: GLOBALS and GLOBALS3D are a horrible names.
# These ares updated in mathics.builtin.graphics in and mathics.builtin.box.graphics3d
GLOBALS = system_symbols_dict({})
GLOBALS3D = system_symbols_dict({})
