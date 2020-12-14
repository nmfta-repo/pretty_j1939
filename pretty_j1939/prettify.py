from pretty_j1939.parse import init_j1939db, get_describer


class Prettyfier:
    """ A wrapper class around the functions defined in the parse file"""
    """Simply initiate an object of this class and use the describer to pass message id and data"""

    def __init__(self, da_json: str, real_time=False,
                 include_transport_rawdata=False, describe_pgns=True,
                 describe_spns=True, describe_transport_layer=True, describe_link_layer=True,
                 include_na=False):
        init_j1939db(da_json)
        self.describer = get_describer(describe_pgns=describe_pgns,
                                       describe_spns=describe_spns,
                                       describe_link_layer=describe_link_layer,
                                       describe_transport_layer=describe_transport_layer,
                                       include_transport_rawdata=include_transport_rawdata,
                                       include_na=include_na, real_time=real_time)
