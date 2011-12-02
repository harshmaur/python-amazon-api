import re
from amazonproduct.contrib.cart import Cart, Item

from amazonproduct.errors import AWSError
from amazonproduct.processors import BaseResultPaginator, BaseProcessor
from amazonproduct.utils import import_module


implementations = [
    'lxml.etree',
    'xml.etree.cElementTree',
    'xml.etree.ElementTree',
    'cElementTree',
    'elementtree.ElementTree',
]

def load_elementtree_module(*modules):
    """
    Returns the first importable ElementTree implementation from a list of
    modules. If ``modules`` is omitted :data:`implementations` is used.
    """
    if not modules:
        modules = implementations
    for mod in modules:
        try:
            return import_module(mod)
        except ImportError:
            pass
    raise ImportError(
        "Couldn't find any of the ElementTree implementations in %s!" % (
            list(modules), ))

etree = load_elementtree_module()


_nsreg = re.compile('^({.+?})')
def extract_nspace(element):
    """
    Extracts namespace from XML element. If no namespace is found, ``''``
    (empty string) is returned.
    """
    m = _nsreg.search(element.tag)
    if m: return m.group(1)
    return ''


class Processor (BaseProcessor):

    def parse(self, fp):
        root = etree.parse(fp).getroot()
        ns = extract_nspace(root)
        errors = root.findall('.//%sError' % ns)
        for error in errors:
            code = error.findtext('./%sCode' % ns)
            msg = error.findtext('./%sMessage' % ns)
            raise AWSError(code, msg)
        return root

    def __repr__(self):
        return '<%s using %s at %s>' % (
            self.__class__.__name__, etree.__name__, hex(id(self)))

    @classmethod
    def parse_cart(cls, node):
        """
        Returns an instance of :class:`amazonproduct.contrib.Cart` based on
        information extracted from ``node``.
        """
        _nspace = extract_nspace(node)
        _xpath = lambda path: path.replace('{}', _nspace)
        root = node.find(_xpath('.//{}Cart'))


        cart = Cart()
        cart.cart_id = root.findtext(_xpath('./{}CartId'))
        cart.hmac = root.findtext(_xpath('./{}HMAC'))
        cart.url = root.findtext(_xpath('./{}PurchaseURL'))

        def parse_item(item_node):
            from lxml.etree import tostring
            print tostring(item_node, pretty_print=True)
            item = Item()
            item.item_id = item_node.findtext(_xpath('./{}CartItemId'))
            item.asin = item_node.findtext(_xpath('./{}ASIN'))
            item.seller = item_node.findtext(_xpath('./{}SellerNickname'))
            item.quantity = int(item_node.findtext(_xpath('./{}Quantity')))
            item.title = item_node.findtext(_xpath('./{}Title'))
            item.product_group = item_node.findtext(_xpath('./{}ProductGroup'))
            item.price = (
                int(item_node.findtext(_xpath('./{}Price/{}Amount'))),
                item_node.findtext(_xpath('./{}Price/{}CurrencyCode')))
            item.total = (
                int(item_node.findtext(_xpath('./{}ItemTotal/{}Amount'))),
                item_node.findtext(_xpath('./{}ItemTotal/{}CurrencyCode')))
            return item

        try:
            for item_node in root.findall(_xpath('./{}CartItems/{}CartItem')):
                cart.items.append(parse_item(item_node))
            cart.subtotal = (node.SubTotal.Amount, node.SubTotal.CurrencyCode)
        except AttributeError:
            cart.subtotal = (None, None)
        return cart

    @classmethod
    def load_paginator(cls, type_):
        return {
            'ItemPage': ItemPaginator,
        }[type_]


class XPathPaginator (BaseResultPaginator):

    """
    Result paginator using XPath expressions to extract page and result
    information from XML.
    """

    counter = current_page_xpath = total_pages_xpath = total_results_xpath = None

    def extract_data(self, root):
        nspace = extract_nspace(root)
        def fetch_value(xpath, default):
            try:
                path = xpath.replace('{}', nspace)
                node = root.findtext(path)
                return int(node)
            except (ValueError, TypeError):
                return default
        return map(lambda a: fetch_value(*a), [
            (self.current_page_xpath, 1),
            (self.total_pages_xpath, 0),
            (self.total_results_xpath, 0)
        ])


class ItemPaginator (XPathPaginator):

    counter = 'ItemPage'
    current_page_xpath = './/{}Items/{}Request/{}ItemSearchRequest/{}ItemPage'
    total_pages_xpath = './/{}Items/{}TotalPages'
    total_results_xpath = './/{}Items/{}TotalResults'

