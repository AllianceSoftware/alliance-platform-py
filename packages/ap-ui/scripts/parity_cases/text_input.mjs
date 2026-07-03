export const component = 'text_input';
export const class_prefixes = [
    'LabeledInput',
    'TextInputBase',
    'focusRing',
    'Label',
    'FormSection',
    'Icon',
];
// The LabeledInput recipe base class is emitted alongside its variant classes by both the JS
// and Python renderers, so exempt it from the "drop parent when child token exists" rule.
export const keep_class_tokens = ['LabeledInput_labeledInput'];

export const cases = [
    {
        name: 'default',
        template: '{% ui "text_input" label="Email" %}{% endui %}',
        buildElement({ React, components }) {
            const { TextInput } = components;
            return React.createElement(TextInput, { label: 'Email' });
        },
        meta: {},
    },
    {
        name: 'name_type_placeholder_default_value',
        template:
            '{% ui "text_input" label="Email" name="email" type="email" placeholder="name@example.com" defaultValue="jane@example.com" %}{% endui %}',
        buildElement({ React, components }) {
            const { TextInput } = components;
            return React.createElement(TextInput, {
                label: 'Email',
                name: 'email',
                type: 'email',
                placeholder: 'name@example.com',
                defaultValue: 'jane@example.com',
            });
        },
        meta: {},
    },
    {
        name: 'description',
        template: '{% ui "text_input" label="Name" description="Shown on your profile" %}{% endui %}',
        buildElement({ React, components }) {
            const { TextInput } = components;
            return React.createElement(TextInput, {
                label: 'Name',
                description: 'Shown on your profile',
            });
        },
        meta: {},
    },
    {
        name: 'invalid_with_error_message',
        template:
            '{% ui "text_input" label="Email" validationState="invalid" errorMessage="Enter a valid email" %}{% endui %}',
        buildElement({ React, components }) {
            const { TextInput } = components;
            return React.createElement(TextInput, {
                label: 'Email',
                validationState: 'invalid',
                errorMessage: 'Enter a valid email',
            });
        },
        meta: {},
    },
    {
        name: 'invalid_error_replaces_description',
        template:
            '{% ui "text_input" label="Email" validationState="invalid" errorMessage="Enter a valid email" description="Your work email" %}{% endui %}',
        buildElement({ React, components }) {
            const { TextInput } = components;
            return React.createElement(TextInput, {
                label: 'Email',
                validationState: 'invalid',
                errorMessage: 'Enter a valid email',
                description: 'Your work email',
            });
        },
        meta: {},
    },
    {
        name: 'valid',
        template: '{% ui "text_input" label="Email" validationState="valid" %}{% endui %}',
        buildElement({ React, components }) {
            const { TextInput } = components;
            return React.createElement(TextInput, { label: 'Email', validationState: 'valid' });
        },
        meta: {},
    },
    {
        name: 'disabled',
        template: '{% ui "text_input" label="Email" isDisabled=True %}{% endui %}',
        buildElement({ React, components }) {
            const { TextInput } = components;
            return React.createElement(TextInput, { label: 'Email', isDisabled: true });
        },
        meta: {},
    },
    {
        name: 'readonly',
        template: '{% ui "text_input" label="Code" value="ABC123" isReadOnly=True %}{% endui %}',
        buildElement({ React, components }) {
            const { TextInput } = components;
            return React.createElement(TextInput, {
                label: 'Code',
                value: 'ABC123',
                isReadOnly: true,
            });
        },
        meta: {},
    },
    {
        name: 'required',
        template: '{% ui "text_input" label="Email" isRequired=True %}{% endui %}',
        buildElement({ React, components }) {
            const { TextInput } = components;
            return React.createElement(TextInput, { label: 'Email', isRequired: true });
        },
        meta: {},
    },
    {
        name: 'label_position_side_align_end',
        template: '{% ui "text_input" label="Email" labelPosition="side" labelAlign="end" %}{% endui %}',
        buildElement({ React, components }) {
            const { TextInput } = components;
            return React.createElement(TextInput, {
                label: 'Email',
                labelPosition: 'side',
                labelAlign: 'end',
            });
        },
        meta: {},
    },
    {
        name: 'input_size_md',
        template: '{% ui "text_input" label="Email" inputSize="md" %}{% endui %}',
        buildElement({ React, components }) {
            const { TextInput } = components;
            return React.createElement(TextInput, { label: 'Email', inputSize: 'md' });
        },
        meta: {},
    },
    {
        name: 'addon_before_and_after',
        template: '{% ui "text_input" label="Website" addonBefore="https://" addonAfter=".com" %}{% endui %}',
        buildElement({ React, components }) {
            const { TextInput } = components;
            return React.createElement(TextInput, {
                label: 'Website',
                addonBefore: 'https://',
                addonAfter: '.com',
            });
        },
        meta: {},
    },
    {
        name: 'custom_class_names',
        template:
            '{% ui "text_input" label="Email" className="custom-root" inputClassName="custom-input" %}{% endui %}',
        buildElement({ React, components }) {
            const { TextInput } = components;
            return React.createElement(TextInput, {
                label: 'Email',
                className: 'custom-root',
                inputClassName: 'custom-input',
            });
        },
        meta: {},
    },
    {
        name: 'caller_id_and_aria_describedby',
        template:
            '{% ui "text_input" label="Email" id="my-id" aria_describedby="external-desc" description="Some description" %}{% endui %}',
        buildElement({ React, components }) {
            const { TextInput } = components;
            return React.createElement(TextInput, {
                label: 'Email',
                id: 'my-id',
                'aria-describedby': 'external-desc',
                description: 'Some description',
            });
        },
        meta: {},
    },
];
