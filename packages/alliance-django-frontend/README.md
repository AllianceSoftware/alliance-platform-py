# Alliance Platform Django Frontend

A library for integrating the [Alliance Platform React library](https://github.com/AllianceSoftware/alliance-platform-js) into a Django project.

Uses [Vite](https://vitejs.dev/) to bundle Javascript and perform server-side rendering, and supplies a number of templatetags to easily embed Alliance Platform React components into Django templates.

* [Installation](#installation)
* [Usage](#usage)
    * [Alliance UI](#alliance-ui)
    * [Bundler](#bundler)
    * [Templates](#templates)
    * [Template Tags](#template-tags)

## Installation

`pip install alliance-django-frontend`

## System Requirements

* Supports django 4.2 and 5.0
* Python >=3.8

## Usage

### Alliance UI

A collection of built-in template tags for easily using Alliance UI React components in Django templates.


A templatetag (for example, Button) can be inserted in a template using the syntax:
```html
{% Button variant="outlined" type="submit" %}Submit{% endButton %}
```
Components can be nested, e.g.
```html
{% MenuBar %}
    {% Menubar.SubMenu %}
        {% Menubar.Item %}Item{% endMenubar.Item %}
    {% endMenubar.SubMenu %}
{% endMenuBar %}
```

Keyword arguments to the tag will be automatically passed as props to the React component.

#### Available Tags

* Button
* ButtonGroup
* DatePicker
* Icon
* InlineAlert
* Menubar
* Menubar.SubMenu
* Menubar.Item
* Menubar.Section
* Pagination
* Table
* TableHeader
* TableBody
* ColumnHeaderLink
* Column
* Row
* Cell
* TimeInput
* Fragment
* raw_html

The following functions are also available:

# utils.get_module_import_source

Given the name of the export within `alliance-platform-js/ui`, creates the javascript import specification for the specified component.

### Bundler
### Templates
### Template Tags
