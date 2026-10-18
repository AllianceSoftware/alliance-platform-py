from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from typing import cast
from unittest import mock

from alliance_platform.codegen.printer import TypescriptPrinter
from alliance_platform.frontend.bundler.context import BundlerAssetContext
from alliance_platform.frontend.templatetags.react import ComponentProps
from alliance_platform.frontend.templatetags.react import ComponentSourceCodeGenerator
from alliance_platform.ui.forms.renderers import StaticFormRenderer
from alliance_platform.ui.forms.renderers import form_input_context_key
from allianceutils.auth.permission import AmbiguousGlobalPermissionWarning
from allianceutils.tests.util import warning_filter
from bs4 import BeautifulSoup
import django
from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.forms.renderers import TemplatesSetting
from django.forms.renderers import get_default_renderer
from django.http import QueryDict
from django.template import Context
from django.template import Origin
from django.template import Template
from django.template import TemplateDoesNotExist
from django.test import TestCase
from django.test import override_settings
from django.urls import reverse
from django.utils.safestring import mark_safe
from test_alliance_platform_ui.factory import UserFactory
from test_alliance_platform_ui.models import User

from .parity.base import HtmlUIParityTestCase
from .test_utils import override_ap_frontend_settings
from .test_utils.bundler import TestViteBundler
from .test_utils.bundler import bundler_kwargs
from .test_utils.bundler import bypass_frontend_resource_registry
from .test_utils.bundler import run_prettier


class TestForm(forms.Form):
    first_name = forms.CharField(label="First name", max_length=100)
    second_name = forms.CharField(label="Last name", max_length=100)


class ReactTextInputWidget(forms.TextInput):
    template_name = "test_widgets/react_text_input.html"


class ReactHelpTextForm(forms.Form):
    email = forms.EmailField(
        label="Email",
        help_text="Use your <strong>work</strong> email",
        widget=ReactTextInputWidget,
    )


class ReactSafeErrorForm(forms.Form):
    code = forms.CharField(label="Code", widget=ReactTextInputWidget)

    def clean_code(self):
        raise ValidationError(mark_safe("Use <strong>letters</strong>"))


STATIC_FORM_RENDERER = "alliance_platform.ui.forms.renderers.StaticFormRenderer"
#: Each directory holds a project's own template for a Django widget template
WIDGET_OVERRIDES_DIR = (
    Path(__file__).resolve().parent.parent / "test_alliance_platform_ui/form_widget_overrides"
)


class StaticWidgetForm(forms.Form):
    name = forms.CharField(label="Name", help_text="Your full name", max_length=50)
    email = forms.EmailField(label="Email")
    age = forms.IntegerField(label="Age", min_value=0)
    notes = forms.CharField(label="Notes", widget=forms.Textarea, required=False)
    token = forms.CharField(widget=forms.HiddenInput, required=False)


class StaticChoiceWidgetForm(forms.Form):
    subscribe = forms.BooleanField(label="Subscribe", help_text="One email a month", required=False)
    colour = forms.ChoiceField(
        label="Colour",
        help_text="Pick one",
        choices=[("red", "Red"), ("green", "Green"), ("blue", "Blue")],
        widget=forms.RadioSelect,
    )
    pets = forms.MultipleChoiceField(
        label="Pets",
        choices=[("Mammals", [("cat", "Cat"), ("dog", "Dog")]), ("fish", "Fish")],
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )


class RawDescriptionWidget(forms.TextInput):
    """Widget template that outputs ``extra_widget_props.description`` directly."""

    template_name = "test_widgets/raw_description.html"


class RawDescriptionForm(forms.Form):
    plain = forms.CharField(label="Plain", help_text="No markup here", widget=RawDescriptionWidget)


test_development_bundler = TestViteBundler(
    **bundler_kwargs,  # type: ignore[arg-type]
    mode="development",
)


def clear_default_renderer_cache() -> None:
    """Clear the ``lru_cache`` on ``get_default_renderer()``.

    Django 4.2 does not clear it when ``FORM_RENDERER`` is overridden (5.0+ does), so a renderer
    cached by an earlier test would leak into tests that override ``FORM_RENDERER``.
    """
    # django-stubs types get_default_renderer without its lru_cache wrapper
    get_default_renderer.cache_clear()  # type: ignore[attr-defined]


@override_ap_frontend_settings(
    # We rely on this in _get_debug_tree
    DEBUG_COMPONENT_OUTPUT=True,
    BUNDLER=test_development_bundler,
)
@override_settings(ROOT_URLCONF="test_alliance_platform_ui.urls")
@warning_filter("ignore", category=AmbiguousGlobalPermissionWarning)
class FormRenderingTestCase(TestCase):
    PERM = "test_utils.link_is_allowed"

    def setUp(self) -> None:
        # Cleared on both sides of each test so no test sees a renderer cached by another
        clear_default_renderer_cache()
        self.bundler_context = BundlerAssetContext(
            frontend_resource_registry=bypass_frontend_resource_registry, skip_checks=True
        )
        self.bundler_context.__enter__()
        self.test_production_bundler = TestViteBundler(
            **bundler_kwargs,  # type: ignore[arg-type]
            mode="production",
        )

        self.test_development_bundler = TestViteBundler(
            **bundler_kwargs,  # type: ignore[arg-type]
            mode="development",
        )
        self.dev_url = self.test_development_bundler.dev_server_url

    def tearDown(self):
        self.bundler_context.__exit__(None, None, None)
        clear_default_renderer_cache()

    def _get_debug_tree(self, template_contents: str, **kwargs: dict):
        def patch_debug_tree(self, props: ComponentProps, include_template_origin=True):
            # Like the default implementation except we never include template origin string
            printer = TypescriptPrinter(jsx_transform=None, codegen_target="file")
            generator = ComponentSourceCodeGenerator(self)
            jsx_element = generator.create_jsx_element_node(self, props, False)
            return printer.print(jsx_element)

        with mock.patch(
            "alliance_platform.frontend.templatetags.react.ComponentNode.print_debug_tree",
            patch_debug_tree,
        ):
            template = Template("{% load react %}" + template_contents)
            context = Context(kwargs)
            context.template = template
            contents = template.render(context)
            code = contents.split("<!--").pop().split("-->").pop(0)
            return code.strip()

    def assertComponentEqual(self, template_code, expected_output, **kwargs):
        self.assertEqual(
            run_prettier(self._get_debug_tree(template_code, **kwargs)),
            run_prettier(expected_output),
        )

    def get_user(self) -> User:
        user = cast(User, UserFactory(is_superuser=True))
        return user

    @contextmanager
    def setup_overrides(self):
        with override_ap_frontend_settings(BUNDLER=self.test_development_bundler):
            with BundlerAssetContext(
                skip_checks=True, frontend_resource_registry=bypass_frontend_resource_registry
            ):
                yield

    def test_form_input_requires_renderer(self):
        user = self.get_user()

        with self.setup_overrides():
            with override_settings(FORM_RENDERER="django.forms.renderers.DjangoTemplates"):
                with self.assertWarns(
                    UserWarning,
                    msg="form_input tag should only be used with 'FormInputContextRenderer'",
                ):
                    self.client.get(reverse("update_user", kwargs={"pk": user.pk}), follow=True)

    def test_renderer_handles_context_key(self):
        user = self.get_user()
        response = self.client.get(reverse("update_user", kwargs={"pk": user.pk}), follow=True)
        for context_value in response.context:
            context_dict = context_value.dicts[1]
            if "widget" in context_dict and "attrs" in context_dict["widget"]:
                # check that context key is removed from widget attrs
                self.assertFalse(form_input_context_key in context_dict["widget"]["attrs"])
                # check that context information has been added to top level context
                self.assertTrue("extra_widget_props" in context_dict)

    def test_form_input_html_help_text_react_widget(self):
        """HTML help_text should reach React widgets as nested elements (via RenderableContent)"""
        self.assert_react_help_text_widget()

    def test_form_input_error_marked_safe_react_widget(self):
        """An error marked safe reaches React widgets as nested elements (via RenderableContent)"""
        output = run_prettier(
            self._get_debug_tree(
                """
                {% load alliance_platform.form %}
                {% form my_form %}{% form_input my_form.code %}{% endform %}""",
                my_form=ReactSafeErrorForm(data={"code": "123"}),
            )
        )
        self.assertIn('errorMessage={["Use ", <strong>letters</strong>]}', output)
        self.assertIn('validationState="invalid"', output)

    @override_settings(FORM_RENDERER=STATIC_FORM_RENDERER)
    def test_static_form_renderer_keeps_a_widget_template_of_its_own(self):
        self.assert_react_help_text_widget()

    def assert_react_help_text_widget(self):
        # Django only links help text to the widget through aria-describedby from 5.0
        help_text_attrs = 'aria-describedby="id_email_helptext"' if django.VERSION >= (5, 0) else ""
        self.assertComponentEqual(
            """
            {% load alliance_platform.form %}
            {% form my_form %}{% form_input my_form.email %}{% endform %}""",
            """<TextInput
              type="text"
              name="email"
              defaultValue={null}
              maxLength="320"
              required={true}
              %(help_text_attrs)s
              id="id_email"
              label="Email"
              errorMessage=""
              validationState={null}
              description={["Use your ", <strong>work</strong>, " email"]}
              isRequired={true}
            />"""
            % {"help_text_attrs": help_text_attrs},
            my_form=ReactHelpTextForm(),
        )

    def test_html_form_nested_components(self):
        """Test that everything in a {% form %} tag is rendered as expected when nested within a component"""
        self.assertComponentEqual(
            """
            {% load react %}
            {% load alliance_platform.form %}
            {% component "div" %}{% form my_form %} <form> {% component "input" %}{% endcomponent %}  </form> {% endform %}{% endcomponent %}""",
            """<div><form><input /></form></div>""",
            my_form=TestForm(),
        )

        self.assertComponentEqual(
            """
            {% load react %}
            {% load alliance_platform.form %}
            {% component "div" %}{% if 1 %} <form> {% component "input" %}{% endcomponent %} {% component "span" %}{% endcomponent %} </form> {% endif %}{% endcomponent %}""",
            """<div><form><input /><span /></form></div>""",
            my_form=TestForm(),
        )

        self.assertComponentEqual(
            """
            {% load react %}
            {% load alliance_platform.form %}
            {% component "div" %}{% if 0 %} <form> {% component "input" %}{% endcomponent %} {% component "span" %}{% endcomponent %} </form> {% endif %}{% endcomponent %}""",
            """<div />""",
            my_form=TestForm(),
        )


@override_settings(FORM_RENDERER=STATIC_FORM_RENDERER)
class StaticFormRendererTestCase(HtmlUIParityTestCase):
    """StaticFormRenderer renders Django's text, number and text area widget templates as static
    components."""

    def setUp(self):
        clear_default_renderer_cache()

    def tearDown(self):
        clear_default_renderer_cache()

    def render_form(self, form: forms.Form) -> str:
        with self.setup_render_context():
            with self.capture_diagnostics() as diagnostics:
                output = self.render_ui_template(
                    "{% load alliance_platform.form %}{% form my_form %}"
                    "{% for field in my_form.visible_fields %}{% form_input field %}{% endfor %}"
                    "{% for field in my_form.hidden_fields %}{{ field }}{% endfor %}"
                    "{% endform %}",
                    {"my_form": form},
                )
        self.assertEqual(diagnostics, [])
        return output

    @contextmanager
    def project_widget_templates(self, directory: str) -> Iterator[None]:
        """Add a project template directory from ``WIDGET_OVERRIDES_DIR``."""
        templates = [{**settings.TEMPLATES[0], "DIRS": [WIDGET_OVERRIDES_DIR / directory]}]
        with override_settings(TEMPLATES=templates):
            yield

    def test_renders_text_number_and_text_area_widgets_as_static_components(self):
        form = StaticWidgetForm(
            data={"name": "Jane", "email": "jane@", "age": "5", "notes": "Hello", "token": "abc"}
        )
        output = self.render_form(form)

        self.assertEqual(output.count('data-apui="text-input"'), 2)
        self.assertEqual(output.count('data-apui="number-input"'), 1)
        self.assertEqual(output.count('data-apui="text-area"'), 1)
        for field, label in [("name", "Name"), ("email", "Email"), ("age", "Age"), ("notes", "Notes")]:
            with self.subTest(field=field):
                self.assertIn(f'for="id_{field}">{label}', output)
        self.assertRegex(output, r'<input(?=[^>]* type="text")(?=[^>]* name="name")(?=[^>]* value="Jane")')
        self.assertRegex(output, r'<input(?=[^>]* type="email")(?=[^>]* name="email")(?=[^>]* value="jane@")')
        self.assertRegex(output, r'<input(?=[^>]* name="age")(?=[^>]* value="5")')
        self.assertIn('data-apui-number-input-min-value="0"', output)
        self.assertIn(
            '<textarea name="notes" id="id_notes" class="TextInputBase_input">Hello</textarea>', output
        )
        # The help text and error message take the ids Django gives them
        self.assertIn('<div class="LabeledInput_helpText" id="id_name_helptext">Your full name</div>', output)
        self.assertRegex(output, r'<input(?=[^>]* id="id_name")(?=[^>]* aria-describedby="id_name_helptext")')
        self.assertIn(
            '<div class="LabeledInput_helpText" id="id_email_error">Enter a valid email address.</div>',
            output,
        )
        self.assertRegex(output, r'<input(?=[^>]* id="id_email")(?=[^>]* aria-describedby="id_email_error")')
        # Django's template still renders a hidden input
        self.assertIn('<input type="hidden" name="token" value="abc" id="id_token">', output)

    def test_renders_checkbox_radio_and_checkbox_select_widgets_as_static_components(self):
        form = StaticChoiceWidgetForm(data={"subscribe": "on", "colour": "green", "pets": ["dog", "fish"]})
        soup = BeautifulSoup(self.render_form(form), "html.parser")

        # The checkbox's label is the field's, beside the box
        checkbox = soup.select_one('[data-apui="checkbox"]:not([data-apui="checkbox-group"] *)')
        assert checkbox is not None
        self.assertEqual(checkbox.get_text(), "Subscribe")
        checkbox_input = checkbox.select_one("input")
        assert checkbox_input is not None
        self.assertEqual(checkbox_input["type"], "checkbox")
        self.assertEqual(checkbox_input["name"], "subscribe")
        self.assertEqual(checkbox_input["id"], "id_subscribe")
        self.assertTrue(checkbox_input.has_attr("checked"))
        self.assertFalse(checkbox_input.has_attr("value"))
        # As React's Checkbox, the checkbox renders neither its help text nor an error message
        self.assertIsNone(soup.find(id="id_subscribe_helptext"))

        # The groups are labelled by their labels and described by their help text
        radio_group = soup.select_one('[role="radiogroup"]')
        assert radio_group is not None
        self.assertEqual(radio_group["id"], "id_colour")
        self.assertEqual(radio_group["aria-labelledby"], "id_colour_label")
        self.assertEqual(soup.find(id="id_colour_label").get_text(), "Colour*")
        self.assertEqual(radio_group["aria-describedby"], "id_colour_helptext")
        self.assertEqual(soup.find(id="id_colour_helptext").get_text(), "Pick one")
        radios = radio_group.select('input[type="radio"]')
        self.assertEqual([radio["id"] for radio in radios], ["id_colour_0", "id_colour_1", "id_colour_2"])
        self.assertEqual({radio["name"] for radio in radios}, {"colour"})
        self.assertEqual([radio["value"] for radio in radios if radio.has_attr("checked")], ["green"])
        for radio in radios:
            self.assertEqual(radio["aria-describedby"], "id_colour_helptext")

        checkbox_group = soup.select_one('[role="group"][data-apui="checkbox-group"]')
        assert checkbox_group is not None
        self.assertEqual(checkbox_group["aria-labelledby"], "id_pets_label")
        pets = checkbox_group.select('input[type="checkbox"]')
        # The options of an optgroup render in the one group
        self.assertEqual([pet["id"] for pet in pets], ["id_pets_0_0", "id_pets_0_1", "id_pets_1"])
        self.assertEqual([pet["value"] for pet in pets], ["cat", "dog", "fish"])
        self.assertEqual([pet["value"] for pet in pets if pet.has_attr("checked")], ["dog", "fish"])

    def test_choice_widget_errors_take_the_ids_django_gives_them(self):
        form = StaticChoiceWidgetForm(data={"subscribe": "on"})
        soup = BeautifulSoup(self.render_form(form), "html.parser")

        radio_group = soup.select_one('[role="radiogroup"]')
        assert radio_group is not None
        self.assertEqual(radio_group["aria-invalid"], "true")
        self.assertEqual(radio_group["data-invalid"], "true")
        # The error message replaces the help text
        self.assertEqual(radio_group["aria-describedby"], "id_colour_error")
        self.assertEqual(soup.find(id="id_colour_error").get_text(), "This field is required.")
        self.assertIsNone(soup.find(id="id_colour_helptext"))
        for radio in radio_group.select("input"):
            self.assertEqual(radio["aria-describedby"], "id_colour_error")

    def test_choice_widgets_submit_the_values_django_reads(self):
        initial = {"subscribe": True, "colour": "blue", "pets": ["cat", "fish"]}
        soup = BeautifulSoup(self.render_form(StaticChoiceWidgetForm(initial=initial)), "html.parser")

        # What a browser submits: the name and value of each checked checkbox and radio
        submitted = QueryDict(mutable=True)
        for control in soup.select("input[checked]"):
            submitted.appendlist(control["name"], control.get("value", "on"))
        form = StaticChoiceWidgetForm(data=submitted)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data, initial)

        # An unchecked checkbox submits nothing, which Django reads as False
        unchecked = BeautifulSoup(
            self.render_form(StaticChoiceWidgetForm(initial={"colour": "red"})), "html.parser"
        )
        self.assertEqual(
            [(control["name"], control.get("value", "on")) for control in unchecked.select("input[checked]")],
            [("colour", "red")],
        )

    def test_widgets_without_django_auto_ids_share_the_document_allocator(self):
        output = self.render_form(StaticWidgetForm(auto_id=False))
        soup = BeautifulSoup(output, "html.parser")
        ids = [element["id"] for element in soup.select("[id]")]
        self.assertEqual(len(ids), len(set(ids)))
        controls = soup.select("input:not([type=hidden]), textarea")
        for control in controls:
            self.assertTrue(control.get("id"))
            self.assertIsNotNone(soup.find("label", attrs={"for": control["id"]}))
            for described_by in control.get("aria-describedby", "").split():
                self.assertIsNotNone(soup.find(id=described_by))

    def test_choice_widgets_without_django_auto_ids_reference_ids_that_render(self):
        output = self.render_form(StaticChoiceWidgetForm(data={}, auto_id=False))
        soup = BeautifulSoup(output, "html.parser")
        ids = [element["id"] for element in soup.select("[id]")]
        self.assertEqual(len(ids), len(set(ids)))
        for element in soup.select("[aria-labelledby], [aria-describedby]"):
            for attribute in ("aria-labelledby", "aria-describedby"):
                for referenced_id in element.get(attribute, "").split():
                    self.assertIsNotNone(soup.find(id=referenced_id), referenced_id)
        # The radio group's label and error message get generated ids
        radio_group = soup.select_one('[role="radiogroup"]')
        assert radio_group is not None
        self.assertRegex(radio_group["aria-labelledby"], r"^apui-radio-group-\d+$")
        self.assertRegex(radio_group["aria-describedby"], r"^apui-radio-group-\d+$")

    def test_maps_each_django_widget_template_to_a_static_template(self):
        renderer = StaticFormRenderer()
        for template_name, static_template_name in renderer.static_widget_templates.items():
            with self.subTest(template=template_name):
                try:
                    TemplatesSetting().get_template(template_name)
                except TemplateDoesNotExist:
                    # tel.html and search.html are new in Django 5.2
                    self.skipTest(f"Django {django.get_version()} has no {template_name}")
                # Compiling a {% ui %} template registers its frontend resources
                with self.setup_render_context():
                    template = renderer.get_template(template_name)
                self.assertTrue(template.origin.name.endswith(f"/templates/{static_template_name}"))

    def test_a_project_widget_template_wins(self):
        with self.project_widget_templates("text"):
            output = self.render_form(StaticWidgetForm())

        self.assertIn('<input type="text" name="name" data-project-widget="text.html">', output)
        # The email input has no template of the project's
        self.assertEqual(output.count('data-apui="text-input"'), 1)
        self.assertEqual(output.count('data-apui="number-input"'), 1)
        self.assertEqual(output.count('data-apui="text-area"'), 1)

    def test_a_project_input_template_wins_for_the_widget_templates_including_it(self):
        with self.project_widget_templates("input"):
            output = self.render_form(StaticWidgetForm())

        for name, input_type in [
            ("name", "text"),
            ("email", "email"),
            ("age", "number"),
            ("token", "hidden"),
        ]:
            with self.subTest(field=name):
                self.assertIn(
                    f'<input type="{input_type}" name="{name}" data-project-widget="input.html">', output
                )
        self.assertNotIn('data-apui="text-input"', output)
        self.assertNotIn('data-apui="number-input"', output)
        # Django's textarea.html does not include input.html
        self.assertEqual(output.count('data-apui="text-area"'), 1)

    def test_a_project_input_template_wins_for_the_checkbox_and_option_widgets(self):
        with self.project_widget_templates("input"):
            output = self.render_form(StaticChoiceWidgetForm())

        # Django's checkbox template includes input.html, and its radio and checkbox select templates
        # render each option through it
        self.assertIn('<input type="checkbox" name="subscribe" data-project-widget="input.html">', output)
        self.assertEqual(
            output.count('<input type="radio" name="colour" data-project-widget="input.html">'), 3
        )
        self.assertNotIn("data-apui=", output)

    def test_a_project_option_template_wins_for_the_radio_and_checkbox_select_widgets(self):
        with self.project_widget_templates("option"):
            output = self.render_form(StaticChoiceWidgetForm())

        self.assertEqual(output.count('data-project-widget="input_option.html"'), 6)
        self.assertNotIn('data-apui="radio-group"', output)
        self.assertNotIn('data-apui="checkbox-group"', output)
        # The checkbox does not render through input_option.html
        self.assertEqual(output.count('data-apui="checkbox"'), 1)

    def test_widget_template_of_its_own_gets_extra_widget_props(self):
        output = self.render_form(RawDescriptionForm())

        self.assertEqual(output, '<span class="raw-description">No markup here</span>')

    def test_templates_of_other_backends_are_left_in_place(self):
        class OtherBackendTemplate:
            # A template another backend loaded from Django's file, with an origin as the Jinja2
            # backend's templates have
            origin = Origin(str(Path(forms.__file__).parent / "templates/django/forms/widgets/textarea.html"))

        template = OtherBackendTemplate()

        def get_template(template_name: str):
            return template if template_name.startswith("django/") else object()

        with mock.patch.object(TemplatesSetting, "get_template", side_effect=get_template):
            self.assertIs(StaticFormRenderer().get_template("django/forms/widgets/textarea.html"), template)
