import React from 'react';
import { Button } from '@alliancesoftware/ui';

export const component = 'button';

export const cases = [
    {
        name: 'default',
        template: '{% ui "button" %}Save{% endui %}',
        buildElement() {
            return React.createElement(Button, null, 'Save');
        },
        meta: {},
    },
    {
        name: 'invalid_variant_warns_and_falls_back',
        template: '{% ui "button" variant="invalid" %}Save{% endui %}',
        buildElement() {
            return React.createElement(Button, { variant: 'invalid' }, 'Save');
        },
        meta: {},
    },
    {
        name: 'anchor_variant',
        template: '{% ui "button" href="/next" color="secondary" size="lg" %}Go{% endui %}',
        buildElement() {
            return React.createElement(Button, { href: '/next', color: 'secondary', size: 'lg' }, 'Go');
        },
        meta: {},
    },
];
