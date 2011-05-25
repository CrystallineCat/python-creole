#!/usr/bin/env python
# coding: utf-8


"""
    python-creole
    ~~~~~~~~~~~~~


    :copyleft: 2008-2011 by python-creole team, see AUTHORS for more details.
    :license: GNU GPL v3 or above, see LICENSE for more details.
"""


import re
import warnings
import inspect
from HTMLParser import HTMLParser

from creole.html2creole.strip_html import strip_html
from creole.html2creole.config import BLOCK_TAGS, IGNORE_TAGS


block_re = re.compile(r'''
    ^<pre> \s* $
    (?P<pre_block>
        (\n|.)*?
    )
    ^</pre> \s* $
    [\s\n]*
''', re.VERBOSE | re.UNICODE | re.MULTILINE)

#------------------------------------------------------------------------------

inline_re = re.compile(r'''
    <pre>
    (?P<pre_inline>
        (\n|.)*?
    )
    </pre>
''', re.VERBOSE | re.UNICODE)

#------------------------------------------------------------------------------

headline_tag_re = re.compile(r"h(\d)", re.UNICODE)




class DocNode:
    """
    A node in the document.
    """
    def __init__(self, kind='', parent=None, attrs=[], content=None, \
                                                                    level=None):
        self.kind = kind

        self.children = []
        self.parent = parent
        if self.parent is not None:
            self.parent.children.append(self)

        self.attrs = dict(attrs)
        if content:
            assert isinstance(content, unicode)
        self.content = content
        self.level = level

    def get_attrs_as_string(self):
        """
        FIXME: Find a better was to do this.

        >>> node = DocNode(attrs={'foo':"bar", u"no":123})
        >>> node.get_attrs_as_string()
        u'foo="bar" no="123"'

        >>> node = DocNode(attrs={"foo":'bar', "no":u"ABC"})
        >>> node.get_attrs_as_string()
        u'foo="bar" no="ABC"'
        """
        attr_list = []
        for key, value in self.attrs.iteritems():
            if not isinstance(value, unicode):
                value = unicode(value)
            value_string = repr(value).lstrip("u").replace(u"'", u'"')
            attr_list.append(u"%s=%s" % (key, value_string))
        return u" ".join(attr_list)

    def __str__(self):
        return str(self.__repr__())

    def __repr__(self):
        return u"<DocNode %s: %r>" % (self.kind, self.content)
#        return u"<DocNode %s (parent: %r): %r>" % (self.kind, self.parent, self.content)

    def debug(self):
        print "_" * 80
        print "\tDocNode - debug:"
        print "str(): %s" % self
        print "attributes:"
        for i in dir(self):
            if i.startswith("_") or i == "debug":
                continue
            print "%20s: %r" % (i, getattr(self, i, "---"))


class DebugList(list):
    def __init__(self, html2creole):
        self.html2creole = html2creole
        super(DebugList, self).__init__()

    def append(self, item):
#        for stack_frame in inspect.stack(): print stack_frame

        line, method = inspect.stack()[1][2:4]
        msg = "%-8s   append: %-35r (%-15s line:%s)" % (
            self.html2creole.getpos(), item,
            method, line
        )
        warnings.warn(msg)
        list.append(self, item)







class Html2CreoleParser(HTMLParser):
    # placeholder html tag for pre cutout areas:
    _block_placeholder = "blockdata"
    _inline_placeholder = "inlinedata"

    def __init__(self, debug=False):
        HTMLParser.__init__(self)

        self.debugging = debug
        if self.debugging:
            warnings.warn(
                message="Html2Creole debug is on! warn every data append."
            )
            self.result = DebugList(self)
        else:
            self.result = []

        self.blockdata = []

        self.root = DocNode("document", None)
        self.cur = self.root

        self.__list_level = 0

    def _pre_cut(self, data, type, placeholder):
        if self.debugging:
            print "append blockdata: %r" % data
        assert isinstance(data, unicode), "blockdata is not unicode"
        self.blockdata.append(data)
        id = len(self.blockdata) - 1
        return u'<%s type="%s" id="%s" />' % (placeholder, type, id)

    def _pre_pre_inline_cut(self, groups):
        return self._pre_cut(groups["pre_inline"], "pre", self._inline_placeholder)

    def _pre_pre_block_cut(self, groups):
        return self._pre_cut(groups["pre_block"], "pre", self._block_placeholder)

    def _pre_pass_block_cut(self, groups):
        content = groups["pass_block"].strip()
        return self._pre_cut(content, "pass", self._block_placeholder)

    _pre_pass_block_start_cut = _pre_pass_block_cut

    def _pre_cut_out(self, match):
        groups = match.groupdict()
        for name, text in groups.iteritems():
            if text is not None:
                if self.debugging:
                    print "%15s: %r (%r)" % (name, text, match.group(0))
                method = getattr(self, '_pre_%s_cut' % name)
                return method(groups)

#        data = match.group("data")

    def feed(self, raw_data):
        assert isinstance(raw_data, unicode), "feed data must be unicode!"
        data = raw_data.strip()

        # cut out <pre> and <tt> areas block tag areas
        data = block_re.sub(self._pre_cut_out, data)
        data = inline_re.sub(self._pre_cut_out, data)

        # Delete whitespace from html code
        data = strip_html(data)

        if self.debugging:
            print "_" * 79
            print "raw data:"
            print repr(raw_data)
            print " -" * 40
            print "cleaned data:"
            print data
            print "-" * 79
#            print clean_data.replace(">", ">\n")
#            print "-"*79

        HTMLParser.feed(self, data)

        return self.root


    #-------------------------------------------------------------------------

    def _upto(self, node, kinds):
        """
        Look up the tree to the first occurence
        of one of the listed kinds of nodes or root.
        Start at the node node.
        """
        while node is not None and node.parent is not None:
            node = node.parent
            if node.kind in kinds:
                break

        return node

    def _go_up(self):
        kinds = list(BLOCK_TAGS) + ["document"]
        self.cur = self._upto(self.cur, kinds)
        self.debug_msg("go up to", self.cur)

    #-------------------------------------------------------------------------

    def handle_starttag(self, tag, attrs):
        self.debug_msg("starttag", "%r atts: %s" % (tag, attrs))

        if tag in IGNORE_TAGS:
            return

        headline = headline_tag_re.match(tag)
        if headline:
            self.cur = DocNode(
                "headline", self.cur, level=int(headline.group(1))
            )
            return

        if tag in ("li", "ul", "ol"):
            if tag in ("ul", "ol"):
                self.__list_level += 1
            self.cur = DocNode(tag, self.cur, attrs, level=self.__list_level)
        elif tag in ("img", "br"):
            # Work-a-round if img or br  tag is not marked as startendtag:
            # wrong: <img src="/image.jpg"> doesn't work if </img> not exist
            # right: <img src="/image.jpg" />
            DocNode(tag, self.cur, attrs)
        else:
            self.cur = DocNode(tag, self.cur, attrs)

    def handle_data(self, data):
        self.debug_msg("data", "%r" % data)
        if isinstance(data, str):
            data = unicode(data)
        DocNode("data", self.cur, content=data)

    def handle_charref(self, name):
        self.debug_msg("charref", "%r" % name)
        DocNode("charref", self.cur, content=name)

    def handle_entityref(self, name):
        self.debug_msg("entityref", "%r" % name)
        DocNode("entityref", self.cur, content=name)

    def handle_startendtag(self, tag, attrs):
        self.debug_msg("startendtag", "%r atts: %s" % (tag, attrs))
        attr_dict = dict(attrs)
        if tag in (self._block_placeholder, self._inline_placeholder):
            id = int(attr_dict["id"])
#            block_type = attr_dict["type"]
            DocNode(
                "%s_%s" % (tag, attr_dict["type"]),
                self.cur,
                content=self.blockdata[id],
#                attrs = attr_dict
            )
        else:
            DocNode(tag, self.cur, attrs)

    def handle_endtag(self, tag):
        if tag in IGNORE_TAGS:
            return

        self.debug_msg("endtag", "%r" % tag)

        if tag == "br": # handled in starttag
            return

        self.debug_msg("starttag", "%r" % self.get_starttag_text())

        if tag in ("ul", "ol"):
            self.__list_level -= 1

        if tag in BLOCK_TAGS:
            self._go_up()
        else:
            self.cur = self.cur.parent

    #-------------------------------------------------------------------------

    def debug_msg(self, method, txt):
        if not self.debugging:
            return
        print "%-8s %8s: %s" % (self.getpos(), method, txt)

    def debug(self, start_node=None):
        """
        Display the current document tree
        """
        print "_" * 80

        if start_node == None:
            start_node = self.root
            print "  document tree:"
        else:
            print "  tree from %s:" % start_node

        print "=" * 80
        def emit(node, ident=0):
            for child in node.children:
                txt = u"%s%s" % (u" " * ident, child.kind)

                if child.content:
                    txt += ": %r" % child.content

                if child.attrs:
                    txt += " - attrs: %r" % child.attrs

                if child.level != None:
                    txt += " - level: %r" % child.level

                print txt
                emit(child, ident + 4)
        emit(start_node)
        print "*" * 80


if __name__ == '__main__':
    import doctest
    print doctest.testmod()
