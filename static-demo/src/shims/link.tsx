// Stand-in for next/link: an ordinary anchor whose href is the route's hash name.
import { forwardRef, type AnchorHTMLAttributes } from "react";
import { toHash } from "../routes";

type Props = Omit<AnchorHTMLAttributes<HTMLAnchorElement>, "href"> & { href: string; prefetch?: boolean; replace?: boolean; scroll?: boolean };

const Link = forwardRef<HTMLAnchorElement, Props>(function Link({ href, prefetch: _p, replace: _r, scroll: _s, ...rest }, ref) {
  const h = href.startsWith("#") ? href : toHash(href);
  return <a ref={ref} href={h} {...rest} />;
});

export default Link;
