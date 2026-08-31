/** @odoo-module **/

// ponytail: Odoo core calls document.activeElement.blur() without a null check
// (SelectMenu bottom-sheet, StockBarcodeKanban onMounted, search panel resize, etc.).
// Safari/iOS and some focus transitions leave activeElement as null →
// TypeError: Cannot read properties of null (reading 'blur').
// Align with Chrome/Firefox: fall back to <body> when nothing is focused.
const activeElementDescriptor = Object.getOwnPropertyDescriptor(
    Document.prototype,
    "activeElement"
);
if (activeElementDescriptor?.get) {
    Object.defineProperty(Document.prototype, "activeElement", {
        configurable: true,
        enumerable: activeElementDescriptor.enumerable,
        get() {
            return activeElementDescriptor.get.call(this) || this.body;
        },
    });
}
