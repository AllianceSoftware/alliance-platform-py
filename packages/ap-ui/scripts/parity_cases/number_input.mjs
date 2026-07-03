export const component = 'number_input';
export const class_prefixes = [
    'LabeledInput',
    'TextInputBase',
    'focusRing',
    'Label',
    'FormSection',
    'Icon',
    'NumberInput',
];
export const keep_class_tokens = ['LabeledInput_labeledInput'];

export const cases = [
    {
        name: 'default',
        template: '{% ui "number_input" label="Quantity" %}{% endui %}',
        buildElement({ React, components }) {
            const { NumberInput } = components;
            return React.createElement(NumberInput, { label: 'Quantity' });
        },
        meta: {},
    },
    {
        name: 'name_and_default_value',
        template: '{% ui "number_input" label="Quantity" name="qty" defaultValue=5 %}{% endui %}',
        buildElement({ React, components }) {
            const { NumberInput } = components;
            return React.createElement(NumberInput, { label: 'Quantity', name: 'qty', defaultValue: 5 });
        },
        meta: {},
    },
    {
        // minValue/maxValue/step have no static DOM representation in the React output (the input is
        // rendered as type="text" with inputmode="numeric" and clamping happens client side), so this
        // case documents that they are accepted without changing the rendered HTML.
        name: 'min_max_step',
        template: '{% ui "number_input" label="Quantity" minValue=1 maxValue=20 step=1 %}{% endui %}',
        buildElement({ React, components }) {
            const { NumberInput } = components;
            return React.createElement(NumberInput, {
                label: 'Quantity',
                minValue: 1,
                maxValue: 20,
                step: 1,
            });
        },
        meta: {},
    },
    {
        name: 'hide_step_buttons',
        template: '{% ui "number_input" label="Price" defaultValue=12.5 hideStepButtons=True %}{% endui %}',
        buildElement({ React, components }) {
            const { NumberInput } = components;
            return React.createElement(NumberInput, {
                label: 'Price',
                defaultValue: 12.5,
                hideStepButtons: true,
            });
        },
        meta: {},
    },
    {
        name: 'invalid_with_error_message',
        template:
            '{% ui "number_input" label="Age" name="age" isInvalid=True errorMessage="Age is required" %}{% endui %}',
        buildElement({ React, components }) {
            const { NumberInput } = components;
            return React.createElement(NumberInput, {
                label: 'Age',
                name: 'age',
                isInvalid: true,
                errorMessage: 'Age is required',
            });
        },
        meta: {},
    },
    {
        name: 'disabled',
        template: '{% ui "number_input" label="Quantity" isDisabled=True %}{% endui %}',
        buildElement({ React, components }) {
            const { NumberInput } = components;
            return React.createElement(NumberInput, { label: 'Quantity', isDisabled: true });
        },
        meta: {},
    },
    {
        name: 'addon_after_with_step_buttons',
        template: '{% ui "number_input" label="Price" addonAfter="AUD" defaultValue=12.5 %}{% endui %}',
        buildElement({ React, components }) {
            const { NumberInput } = components;
            return React.createElement(NumberInput, {
                label: 'Price',
                addonAfter: 'AUD',
                defaultValue: 12.5,
            });
        },
        meta: {},
    },
    {
        name: 'custom_class_names',
        template:
            '{% ui "number_input" label="Quantity" className="custom-root" inputClassName="custom-input" %}{% endui %}',
        buildElement({ React, components }) {
            const { NumberInput } = components;
            return React.createElement(NumberInput, {
                label: 'Quantity',
                className: 'custom-root',
                inputClassName: 'custom-input',
            });
        },
        meta: {},
    },
];
