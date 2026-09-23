import { Link } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { LOGO } from "./shared";
import { CartButton } from "./Cart";

export function PageShell({ children, testId, showCart = true }) {
  return <div className="site order-page" data-testid={testId}>
    <nav className="nav static-nav">
      <Link className="brand" to="/"><img src={LOGO} alt="7teen Stories Cafe logo" /><span>7teen<br /><i>Stories</i></span></Link>
      <div className="order-nav-right"><Link to="/#menu" className="back-link" data-testid="back-to-menu-link"><ArrowLeft size={14} /> Menu</Link>{showCart && <CartButton />}</div>
    </nav>
    <main className="order-main">{children}</main>
    <footer className="order-footer"><small>© 2026 7teen Stories Cafe · Every visit is another story.</small></footer>
  </div>;
}
