/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component } from "@odoo/owl";

export class TestOverviewMap extends Component {
    static template = "transport_management.TestOverviewMap";
    static props = {
        action: { type: Object, optional: true },
        "*": true,
    };

    setup() {
        console.log("TestOverviewMap loaded successfully!");
    }
}

registry.category("actions").add("test_transport_overview", TestOverviewMap);