/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, useState, useRef, onWillUnmount } from "@odoo/owl";

export class McitRagSystray extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.inputRef = useRef("input");
        this.state = useState({
            open: false,
            messages: [
                {
                    role: "assistant",
                    text: "Ask me anything about Grants, Budgets, Compliance, "
                        + "Reports, Advances, or Fund Receipts. I'll only "
                        + "answer using DoFAS records you have access to.",
                    sources: [],
                },
            ],
            question: "",
            loading: false,
        });
        this._onKeydownGlobal = (ev) => {
            if (ev.key === "Escape" && this.state.open) {
                this.close();
            }
        };
        window.addEventListener("keydown", this._onKeydownGlobal);
        onWillUnmount(() => {
            window.removeEventListener("keydown", this._onKeydownGlobal);
        });
    }

    toggle() {
        this.state.open = !this.state.open;
        if (this.state.open) {
            // wait for the panel to render before focusing it
            setTimeout(() => this.inputRef.el && this.inputRef.el.focus(), 0);
        }
    }

    close() {
        this.state.open = false;
    }

    async send() {
        const question = this.state.question.trim();
        if (!question || this.state.loading) {
            return;
        }
        this.state.messages.push({ role: "user", text: question, sources: [] });
        this.state.question = "";
        this.state.loading = true;
        try {
            const result = await this.orm.call("mcit.rag.query", "ask", [question]);
            this.state.messages.push({
                role: "assistant",
                text: result.answer,
                sources: result.sources || [],
            });
        } catch (error) {
            const msg = (error && error.data && error.data.message)
                || "Something went wrong answering that question.";
            this.state.messages.push({ role: "assistant", text: msg, sources: [], isError: true });
        } finally {
            this.state.loading = false;
            this.inputRef.el && this.inputRef.el.focus();
        }
    }

    onKeydown(ev) {
        if (ev.key === "Enter" && !ev.shiftKey) {
            ev.preventDefault();
            this.send();
        }
    }

    openSource(source) {
        this.close();
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: source.model,
            res_id: source.res_id,
            views: [[false, "form"]],
            target: "current",
        });
    }
}
McitRagSystray.template = "mcit_rag_assistant.Systray";

registry.category("systray").add(
    "mcit_rag_assistant.systray",
    { Component: McitRagSystray },
    { sequence: 1 }
);
