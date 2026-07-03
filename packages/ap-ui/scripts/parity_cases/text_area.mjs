export const component = 'text_area';
export const class_prefixes = [
    'LabeledInput',
    'TextInputBase',
    'focusRing',
    'Label',
    'FormSection',
    'Icon',
];
export const keep_class_tokens = ['LabeledInput_labeledInput'];

export const cases = [
    {
        name: 'default',
        template: '{% ui "text_area" label="Notes" %}{% endui %}',
        buildElement({ React, components }) {
            const { TextArea } = components;
            return React.createElement(TextArea, { label: 'Notes' });
        },
        meta: {},
    },
    {
        // `rows`/`cols` are deliberately not covered here: the React TextArea drops them (it
        // relies on runtime autosizing instead), while the Django renderer passes them through
        // as a static-render extension. That behaviour is covered by unit tests.
        name: 'name_placeholder_default_value',
        template:
            '{% ui "text_area" label="Notes" name="notes" placeholder="Write here" defaultValue="Initial text" %}{% endui %}',
        buildElement({ React, components }) {
            const { TextArea } = components;
            return React.createElement(TextArea, {
                label: 'Notes',
                name: 'notes',
                placeholder: 'Write here',
                defaultValue: 'Initial text',
            });
        },
        meta: {},
    },
    {
        name: 'height',
        template: '{% ui "text_area" label="Notes" height="120px" %}{% endui %}',
        buildElement({ React, components }) {
            const { TextArea } = components;
            return React.createElement(TextArea, { label: 'Notes', height: '120px' });
        },
        meta: {},
    },
    {
        name: 'description',
        template: '{% ui "text_area" label="Notes" description="Internal notes only" %}{% endui %}',
        buildElement({ React, components }) {
            const { TextArea } = components;
            return React.createElement(TextArea, {
                label: 'Notes',
                description: 'Internal notes only',
            });
        },
        meta: {},
    },
    {
        name: 'invalid_with_error_message',
        template:
            '{% ui "text_area" label="Notes" validationState="invalid" errorMessage="Notes are required" %}{% endui %}',
        buildElement({ React, components }) {
            const { TextArea } = components;
            return React.createElement(TextArea, {
                label: 'Notes',
                validationState: 'invalid',
                errorMessage: 'Notes are required',
            });
        },
        meta: {},
    },
    {
        name: 'disabled',
        template: '{% ui "text_area" label="Notes" isDisabled=True %}{% endui %}',
        buildElement({ React, components }) {
            const { TextArea } = components;
            return React.createElement(TextArea, { label: 'Notes', isDisabled: true });
        },
        meta: {},
    },
    {
        name: 'readonly',
        template: '{% ui "text_area" label="Notes" defaultValue="Locked" isReadOnly=True %}{% endui %}',
        buildElement({ React, components }) {
            const { TextArea } = components;
            return React.createElement(TextArea, {
                label: 'Notes',
                defaultValue: 'Locked',
                isReadOnly: true,
            });
        },
        meta: {},
    },
    {
        name: 'custom_class_names',
        template:
            '{% ui "text_area" label="Notes" className="custom-root" inputClassName="custom-input" %}{% endui %}',
        buildElement({ React, components }) {
            const { TextArea } = components;
            return React.createElement(TextArea, {
                label: 'Notes',
                className: 'custom-root',
                inputClassName: 'custom-input',
            });
        },
        meta: {},
    },
];
