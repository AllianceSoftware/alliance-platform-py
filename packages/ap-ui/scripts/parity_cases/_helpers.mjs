// Normalisation helpers shared by the parity case modules. The fixture generator passes this
// module to each case module's `normalize(root, testCase, helpers)` and applies
// `normalizeClassAttributes` itself after the module's own normalisation.
//
// Keep this module free of imports: `normalizeClassTokens` is ported to
// `tests/parity/normalizers.py`, and its unit test derives expected values from this file.

export function dedupeTokens(tokens) {
  const seen = new Set();
  return tokens.filter((token) => {
    if (!token || seen.has(token)) {
      return false;
    }
    seen.add(token);
    return true;
  });
}

export function tokenizeClasses(value) {
  if (!value) {
    return [];
  }
  return String(value).trim().split(/\s+/).filter(Boolean);
}

/**
 * Reduce a class attribute to the vanilla-extract tokens a fixture compares.
 *
 * Strips `__hash` suffixes, drops hashed tokens whose scope prefix is not in `allowedPrefixes`
 * (unhashed tokens such as consumer class names are always kept), dedupes, then drops a token
 * when a more specific child token (`<token>_...`) is present, or when it ends in `Base` and a
 * token for its root (`<root>_...`) is present. Tokens in `keepClassTokens` are never dropped by
 * those last two rules.
 */
export function normalizeClassTokens(
  classValue,
  allowedPrefixes,
  keepClassTokens
) {
  const normalized = [];
  for (const originalToken of tokenizeClasses(classValue)) {
    const hashIndex = originalToken.lastIndexOf("__");
    const hadHash = hashIndex !== -1;
    const token = hadHash ? originalToken.slice(0, hashIndex) : originalToken;
    if (!token) {
      continue;
    }

    if (token.includes("_")) {
      const prefix = token.split("_", 1)[0];
      if (hadHash && !allowedPrefixes.has(prefix)) {
        continue;
      }
    } else if (hadHash && !allowedPrefixes.has(token)) {
      continue;
    }
    normalized.push(token);
  }

  const deduped = dedupeTokens(normalized);
  return deduped.filter((token) => {
    if (keepClassTokens.has(token)) {
      return true;
    }
    const hasChildToken = deduped.some(
      (other) => other !== token && other.startsWith(`${token}_`)
    );
    if (hasChildToken) {
      return false;
    }
    if (token.endsWith("Base")) {
      const root = token.slice(0, -4);
      if (
        deduped.some((other) => other !== token && other.startsWith(`${root}_`))
      ) {
        return false;
      }
    }
    return true;
  });
}

export function elements(root) {
  return [root, ...root.querySelectorAll("*")].filter(
    (node) => node.nodeType === 1
  );
}

export function normalizeClassAttributes(
  root,
  allowedPrefixes,
  keepClassTokens
) {
  for (const element of elements(root)) {
    if (!element.hasAttribute("class")) {
      continue;
    }
    const classTokens = normalizeClassTokens(
      element.getAttribute("class"),
      allowedPrefixes,
      keepClassTokens
    );
    if (classTokens.length) {
      element.setAttribute("class", classTokens.join(" "));
    } else {
      element.removeAttribute("class");
    }
  }
}

export function removeAttributeMatching(root, name, value = null) {
  for (const element of elements(root)) {
    if (
      element.hasAttribute(name) &&
      (value === null || element.getAttribute(name) === value)
    ) {
      element.removeAttribute(name);
    }
  }
}

export function normalizeInlineStyles(root) {
  for (const element of elements(root)) {
    const value = element.getAttribute("style");
    if (value !== null) {
      element.setAttribute(
        "style",
        value.replace(/:\s*/g, ": ").replace(/;\s*/g, "; ").trim()
      );
    }
  }
}

// assignInlineVars writes hashed custom property names (`--level__1a2b3c: 1`); the static
// renderers write the same properties, so compare them without the hash.
export function normalizeCssVarHashes(root) {
  for (const element of elements(root)) {
    const style = element.getAttribute("style");
    if (style !== null) {
      element.setAttribute(
        "style",
        style.replace(/(--[\w-]+)__[a-z0-9]+\s*:/g, "$1: ")
      );
    }
  }
}

export function prependAttribute(element, name, value) {
  const attributes = Array.from(element.attributes).map((attribute) => [
    attribute.name,
    attribute.value,
  ]);
  for (const attribute of Array.from(element.attributes)) {
    element.removeAttribute(attribute.name);
  }
  element.setAttribute(name, value);
  for (const [attributeName, attributeValue] of attributes) {
    if (attributeName !== name) {
      element.setAttribute(attributeName, attributeValue);
    }
  }
}

export function collectReferencedReactAriaIds(root, attributeNames) {
  const referenced = new Set();
  for (const element of elements(root)) {
    for (const name of attributeNames) {
      for (const token of (element.getAttribute(name) ?? "").split(/\s+/)) {
        if (token.startsWith("react-aria-")) {
          referenced.add(token);
        }
      }
    }
  }
  return referenced;
}

export function removeUnreferencedReactAriaIds(root, referenced) {
  for (const element of elements(root)) {
    const id = element.getAttribute("id");
    if (id?.startsWith("react-aria-") && !referenced.has(id)) {
      element.removeAttribute("id");
    }
  }
}

// Rewrites react-aria generated ids to the static renderers' `apui-<component>-<n>` scheme, in
// order of first appearance.
export function remapReactAriaIds(root, component) {
  const idMap = new Map();
  const idPrefix = `apui-${component.replaceAll("_", "-")}-`;
  for (const element of elements(root)) {
    for (const attribute of Array.from(element.attributes)) {
      const value = attribute.value.replace(/react-aria-[^"'\s]+/g, (token) => {
        if (!idMap.has(token)) {
          idMap.set(token, `${idPrefix}${idMap.size + 1}`);
        }
        return idMap.get(token);
      });
      if (value !== attribute.value) {
        element.setAttribute(attribute.name, value);
      }
    }
  }
}

// react-aria labels fields with both `<label for>` and an `aria-labelledby` id pair and reserves
// description/error ids that may not render. The static renderers rely on `<label for>` and only
// reference help text that renders, so drop the generated references and remap the ids that are
// still referenced. Used by the input components and the table.
export function normalizeInputComponent(root, component) {
  for (const element of elements(root)) {
    const labelledBy = element.getAttribute("aria-labelledby");
    if (labelledBy !== null) {
      const tokens = labelledBy
        .split(/\s+/)
        .filter((token) => token && !token.startsWith("react-aria-"));
      if (tokens.length) {
        element.setAttribute("aria-labelledby", tokens.join(" "));
      } else {
        element.removeAttribute("aria-labelledby");
      }
    }
  }

  const presentIds = new Set(
    elements(root)
      .map((element) => element.getAttribute("id"))
      .filter((id) => id?.startsWith("react-aria-"))
  );
  for (const element of elements(root)) {
    const describedBy = element.getAttribute("aria-describedby");
    if (describedBy !== null) {
      const tokens = describedBy
        .split(/\s+/)
        .filter(
          (token) =>
            token && (!token.startsWith("react-aria-") || presentIds.has(token))
        );
      if (tokens.length) {
        element.setAttribute("aria-describedby", tokens.join(" "));
      } else {
        element.removeAttribute("aria-describedby");
      }
    }
  }

  const referenced = collectReferencedReactAriaIds(root, [
    "for",
    "aria-controls",
    "aria-errormessage",
    "aria-describedby",
  ]);
  removeUnreferencedReactAriaIds(root, referenced);
  remapReactAriaIds(root, component);
  normalizeInlineStyles(root);
}

// Normalisation for markup containing `Button`s (the button and button_group cases).
export function normalizeButtons(root, testCase) {
  removeAttributeMatching(root, "type", "button");
  // React optimistically marks a sole element as icon-only during SSR. Preserve that state only
  // for cases whose static source can make the same determination without mounting a DOM.
  if (!testCase.preserve_icon_only) {
    removeAttributeMatching(root, "data-icon-only", "true");
  }
}

export function serializeHtml(root) {
  return root.innerHTML.replace(
    /<(area|base|br|col|embed|hr|img|input|link|meta|param|source|track|wbr)([^>]*)>/gi,
    "<$1$2/>"
  );
}
