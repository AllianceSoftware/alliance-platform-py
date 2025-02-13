API
###

.. autofunction:: alliance_platform.pdf.decorators.view_as_pdf

.. autofunction:: alliance_platform.pdf.render.render_pdf

.. autofunction:: alliance_platform.pdf.render.get_default_handlers

Request Handlers
****************

.. autoclass:: alliance_platform.pdf.request_handlers.RequestHandler
    :members:

.. autoclass:: alliance_platform.pdf.request_handlers.RequestHandlerResponse

.. autoclass:: alliance_platform.pdf.request_handlers.RequestHandlerResponseStatus

.. autoclass:: alliance_platform.pdf.request_handlers.DjangoRequestHandler

.. autoclass:: alliance_platform.pdf.request_handlers.StaticHttpRequestHandler

.. autoclass:: alliance_platform.pdf.request_handlers.WhitelistDomainRequestHandler

    .. automethod:: __init__

.. autoclass:: alliance_platform.pdf.request_handlers.PassThroughRequestHandler

.. autoclass:: alliance_platform.pdf.request_handlers.MediaHttpRequestHandler

.. autoclass:: alliance_platform.pdf.request_handlers.CustomRequestHandler
