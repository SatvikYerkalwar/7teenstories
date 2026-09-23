import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowRight, Coffee, Minus, Plus, ShoppingBag, Trash2, X } from "lucide-react";
import { imgUrl, rupee } from "./shared";

const CartContext = createContext(null);
const KEY = "7teen-cart";

export function CartProvider({ children }) {
  const [items, setItems] = useState(() => { try { return JSON.parse(localStorage.getItem(KEY)) || []; } catch { return []; } });
  const [open, setOpen] = useState(false);
  useEffect(() => localStorage.setItem(KEY, JSON.stringify(items)), [items]);
  const value = useMemo(() => ({
    items, open, setOpen,
    add: (p, qty = 1) => setItems(cur => {
      const found = cur.find(i => i.product_id === p.id);
      if (found) return cur.map(i => i.product_id === p.id ? { ...i, quantity: Math.min(20, i.quantity + qty) } : i);
      return [...cur, { product_id: p.id, name: p.name, price: Number(p.price), image_url: p.image_url || "", quantity: qty }];
    }),
    setQty: (id, qty) => setItems(cur => qty <= 0 ? cur.filter(i => i.product_id !== id) : cur.map(i => i.product_id === id ? { ...i, quantity: Math.min(20, qty) } : i)),
    remove: (id) => setItems(cur => cur.filter(i => i.product_id !== id)),
    clear: () => setItems([]),
    count: items.reduce((s, i) => s + i.quantity, 0),
    subtotal: items.reduce((s, i) => s + i.price * i.quantity, 0),
  }), [items, open]);
  return <CartContext.Provider value={value}>{children}<CartDrawer /></CartContext.Provider>;
}
export const useCart = () => useContext(CartContext);

export function CartButton({ className = "" }) {
  const cart = useCart();
  return <button className={`cart-btn ${className}`} onClick={() => cart.setOpen(true)} aria-label="Open cart" data-testid="cart-button">
    <ShoppingBag size={18} /><span className="cart-label">Cart</span>{cart.count > 0 && <span className="cart-count" data-testid="cart-count">{cart.count}</span>}
  </button>;
}

export function AddToCart({ product }) {
  const cart = useCart();
  const [qty, setQty] = useState(1);
  const [added, setAdded] = useState(false);
  if (!product.available) return <div className="order-ctl"><span className="unavailable-tag" data-testid={`unavailable-${product.id}`}>Unavailable</span></div>;
  const add = () => { cart.add(product, qty); setQty(1); setAdded(true); setTimeout(() => setAdded(false), 1400); };
  return <div className="order-ctl" data-testid={`order-controls-${product.id}`}>
    <div className="qty"><button onClick={() => setQty(Math.max(1, qty - 1))} aria-label="Decrease" data-testid={`qty-minus-${product.id}`}><Minus size={13} /></button><span data-testid={`qty-value-${product.id}`}>{qty}</span><button onClick={() => setQty(Math.min(20, qty + 1))} aria-label="Increase" data-testid={`qty-plus-${product.id}`}><Plus size={13} /></button></div>
    <button className={`add-btn ${added ? "added" : ""}`} onClick={add} data-testid={`add-to-cart-${product.id}`}>{added ? "Added ✓" : "Add to Cart"}</button>
  </div>;
}

function CartDrawer() {
  const cart = useCart();
  const navigate = useNavigate();
  useEffect(() => { document.body.style.overflow = cart.open ? "hidden" : ""; return () => { document.body.style.overflow = ""; }; }, [cart.open]);
  useEffect(() => { if (!cart.open) return; const k = e => e.key === "Escape" && cart.setOpen(false); window.addEventListener("keydown", k); return () => window.removeEventListener("keydown", k); }, [cart]);
  if (!cart.open) return null;
  return <div className="drawer-backdrop" onClick={() => cart.setOpen(false)} data-testid="cart-drawer-backdrop">
    <aside className="cart-drawer" onClick={e => e.stopPropagation()} data-testid="cart-drawer">
      <div className="drawer-head"><div><p className="chapter">Your tray</p><h2>Your <em>cart.</em></h2></div><button className="icon-btn" onClick={() => cart.setOpen(false)} aria-label="Close cart" data-testid="cart-close"><X /></button></div>
      {cart.items.length === 0 ? <div className="cart-empty" data-testid="cart-empty"><Coffee size={26} /><p>Your cart is empty.<br />Pick a page from the menu to begin.</p><button className="button dark" onClick={() => { cart.setOpen(false); navigate("/#menu"); }} data-testid="cart-browse-menu">Browse the menu <ArrowRight size={15} /></button></div> :
      <>
        <div className="cart-lines">{cart.items.map(i => <div className="cart-line" key={i.product_id} data-testid={`cart-line-${i.product_id}`}>
          <div className="cart-thumb">{i.image_url ? <img src={imgUrl(i.image_url)} alt={i.name} /> : <Coffee size={18} />}</div>
          <div className="cart-info"><h4>{i.name}</h4><span className="cart-price">{rupee(i.price)}</span>
            <div className="qty small"><button onClick={() => cart.setQty(i.product_id, i.quantity - 1)} aria-label="Decrease" data-testid={`cart-minus-${i.product_id}`}><Minus size={12} /></button><span data-testid={`cart-qty-${i.product_id}`}>{i.quantity}</span><button onClick={() => cart.setQty(i.product_id, i.quantity + 1)} aria-label="Increase" data-testid={`cart-plus-${i.product_id}`}><Plus size={12} /></button></div></div>
          <div className="cart-right"><strong data-testid={`cart-line-total-${i.product_id}`}>{rupee(i.price * i.quantity)}</strong><button className="remove-btn" onClick={() => cart.remove(i.product_id)} aria-label="Remove" data-testid={`cart-remove-${i.product_id}`}><Trash2 size={14} /></button></div>
        </div>)}</div>
        <div className="cart-totals"><div><span>Subtotal</span><span data-testid="cart-subtotal">{rupee(cart.subtotal)}</span></div><div className="grand"><span>Total</span><span data-testid="cart-total">{rupee(cart.subtotal)}</span></div><small>Pay at the café · no online payment needed</small>
          <Link to="/checkout" className="button dark full" onClick={() => cart.setOpen(false)} data-testid="checkout-button">Proceed to Checkout <ArrowRight size={15} /></Link></div>
      </>}
    </aside>
  </div>;
}
