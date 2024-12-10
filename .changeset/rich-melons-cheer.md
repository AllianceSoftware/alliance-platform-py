---
"alliance-platform-frontend": patch
---

Support defining frontend resources more explicitly to facilitate better bundling. For example, ES module usage is now supported such that Vite can bundle the exports you use, rather than all exports for a given file/module. In the template project this reduces bundle size by about 75%.

`FrontendAssetRegistry` has been deprecated in favour of [FrontendResourceRegistry](https://alliance-platform.readthedocs.io/projects/frontend/latest/api.htmlapi.html#alliance_platform.frontend.bundler.resource_registry.FrontendResourceRegistry). In addition, the `FRONTEND_ASSET_REGISTRY` setting
has been renamed to [FRONTEND_RESOURCE_REGISTRY](https://alliance-platform.readthedocs.io/projects/frontend/latest/settings.html#alliance_platform.frontend.settings.AlliancePlatformFrontendSettingsType.FRONTEND_RESOURCE_REGISTRY) but will continue to work with a deprecation warning. Migration is straightforward - 
use the new class and call `add_resource` rather than `add_asset`. You can still pass a `Path` to `add_resource`, but
can be more specific and pass resource instances instead like [ESModuleResource](https://alliance-platform.readthedocs.io/projects/frontend/latest/api.html#alliance_platform.frontend.bundler.frontend_resource.ESModuleResource)
