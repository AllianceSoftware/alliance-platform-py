import { Button, ButtonGroup } from '@alliancesoftware/ui';

export const component = 'button_group';

export const cases = [
    {
        name: 'default',
        template: '{% ui "button_group" %}{% ui "button" %}One{% endui %}{% endui %}',
        buildElement({ React }) {
            return React.createElement(
                ButtonGroup,
                null,
                React.createElement(Button, null, 'One')
            );
        },
        meta: {},
    },
    {
        name: 'slot_defaults_and_child_class_merge',
        template:
            '{% ui "button_group" variant="outlined" color="gray" size="lg" density="compact" align="end" %}{% ui "button" className="custom" %}Two{% endui %}{% endui %}',
        buildElement({ React }) {
            return React.createElement(
                ButtonGroup,
                { variant: 'outlined', color: 'gray', size: 'lg', density: 'compact', align: 'end' },
                React.createElement(Button, { className: 'custom' }, 'Two')
            );
        },
        meta: {},
    },
];
