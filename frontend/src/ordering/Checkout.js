import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowRight, Coffee, Minus, Plus, Trash2 } from "lucide-react";
import { PageShell } from "./PageShell";
import { useCart } from "./Cart";
import { imgUrl, post, rupee } from "./shared";

export default function Checkout() {
  const cart = useCart();
  const navigate = useNavigate();
  const [form, setForm] = useState({ customer_name: "", customer_phone: "", order_type: "dine_in", table_number: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const change = e => setForm({ ...form, [e.target.name]: e.target.value });
  const submit = async e => {
    e.preventDefault(); setError("");
    if (!/^[0-9]{10,15}$/.test(form.customer_phone)) return setError("Enter a valid mobile number (10 digits)");
    if (form.order_type === "dine_in" && !form.table_number.trim()) return setError("Please enter your table number");
    setBusy(true);
    try {
      const order = await post("/orders", { ...form, table_number: form.order_type === "dine_in" ? form.table_number : null, items: cart.items.map(i => ({ product_id: i.product_id, quantity: i.quantity })) });
      cart.clear();
      navigate(`/order/${order.order_number}/confirmed`, { state: { order } });
    } catch (err) { setError(err.message); } finally { setBusy(false); }
  };
  return <PageShell testId="checkout-page" showCart={false}>
    <div className="order-head"><p className="chapter">Chapter 05 <span>— Your Order</span></p><h1>Almost <em>there.</em></h1><p className="order-sub">Tell us who the story is for, and where you'd like it served.</p></div>
    {cart.items.length === 0 ? <div className="empty-menu" data-testid="checkout-empty"><Coffee size={22} /><span>Your cart is empty. <Link to="/#menu" className="inline-link">Return to the menu</Link> to pick something.</span></div> :
    <form className="checkout-grid" onSubmit={submit}>
      <section className="paper-card">
        <h3>Your details</h3>
        <label>Customer name<input name="customer_name" value={form.customer_name} onChange={change} required maxLength={60} placeholder="e.g. Rahul" data-testid="checkout-name-input" /></label>
        <label>Mobile number<input name="customer_phone" type="tel" inputMode="numeric" value={form.customer_phone} onChange={e => setForm({ ...form, customer_phone: e.target.value.replace(/\D/g, "").slice(0, 15) })} required placeholder="10-digit mobile" data-testid="checkout-phone-input" /></label>
        <span className="field-label">Order type</span>
        <div className="type-toggle" data-testid="order-type-toggle">
          <button type="button" className={form.order_type === "dine_in" ? "active" : ""} onClick={() => setForm({ ...form, order_type: "dine_in" })} data-testid="order-type-dine-in">Dine-in</button>
          <button type="button" className={form.order_type === "takeaway" ? "active" : ""} onClick={() => setForm({ ...form, order_type: "takeaway", table_number: "" })} data-testid="order-type-takeaway">Takeaway</button>
        </div>
        {form.order_type === "dine_in" && <label>Table number<input name="table_number" value={form.table_number} onChange={change} maxLength={10} placeholder="e.g. 4" data-testid="checkout-table-input" /></label>}
        <div className="pay-note"><small>PAYMENT</small><strong>Pay at Café</strong><p>Settle the bill at the counter when you collect or finish your order.</p></div>
      </section>
      <section className="paper-card summary-card" data-testid="order-summary">
        <h3>Order summary</h3>
        <div className="summary-lines">{cart.items.map(i => <div className="summary-line" key={i.product_id} data-testid={`summary-line-${i.product_id}`}>
          <div className="cart-thumb">{i.image_url ? <img src={imgUrl(i.image_url)} alt={i.name} /> : <Coffee size={16} />}</div>
          <div className="cart-info"><h4>{i.name}</h4><span className="cart-price">{rupee(i.price)} each</span>
            <div className="qty small"><button type="button" onClick={() => cart.setQty(i.product_id, i.quantity - 1)} aria-label="Decrease" data-testid={`summary-minus-${i.product_id}`}><Minus size={12} /></button><span>{i.quantity}</span><button type="button" onClick={() => cart.setQty(i.product_id, i.quantity + 1)} aria-label="Increase" data-testid={`summary-plus-${i.product_id}`}><Plus size={12} /></button></div></div>
          <div className="cart-right"><strong>{rupee(i.price * i.quantity)}</strong><button type="button" className="remove-btn" onClick={() => cart.remove(i.product_id)} aria-label="Remove" data-testid={`summary-remove-${i.product_id}`}><Trash2 size={13} /></button></div>
        </div>)}</div>
        <div className="cart-totals"><div><span>Subtotal</span><span data-testid="summary-subtotal">{rupee(cart.subtotal)}</span></div><div className="grand"><span>Total</span><span data-testid="summary-total">{rupee(cart.subtotal)}</span></div>
          {error && <p className="form-error" data-testid="checkout-error">{error}</p>}
          <button className="button dark full" disabled={busy} data-testid="place-order-button">{busy ? "Placing order…" : "Place Order"} <ArrowRight size={15} /></button>
          <small>Final total is calculated by the café using current menu prices.</small></div>
      </section>
    </form>}
  </PageShell>;
}
