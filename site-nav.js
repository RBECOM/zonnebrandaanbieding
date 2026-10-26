(() => {
  const header = document.querySelector('.site-header');
  if (!header) return;
  header.querySelector('nav')?.remove();
  const nav = document.createElement('nav');
  nav.className = 'category-nav';
  nav.setAttribute('aria-label', 'Hoofdnavigatie');
  nav.innerHTML = `<a href="aanbiedingen.html">Alle aanbiedingen</a><details><summary>Gebruik</summary><div><a href="zonnebrand-lichaam.html">Lichaam</a><a href="zonnebrand-gezicht.html">Gezicht</a><a href="zonnebrand-kinderen.html">Kinderen</a><a href="zonnebrand-wintersport.html">Wintersport</a></div></details><details><summary>Productsoort</summary><div><a href="zonnebrandcreme-lotion.html">Crème & lotion</a><a href="zonnebrandspray.html">Spray</a><a href="zonnebrandfluid.html">Fluid</a><a href="zonnebrandstick.html">Stick</a><a href="zonnebrandolie.html">Olie</a></div></details><details><summary>Factor</summary><div><a href="spf-30-of-50.html">SPF 30 of 50?</a><a href="aanbiedingen.html?spf=30">SPF 30</a><a href="aanbiedingen.html?spf=50">SPF 50</a></div></details><a href="vragen.html">Zonnebrandvragen</a><details class="mobile-menu"><summary>Menu</summary><div><a href="aanbiedingen.html">Alle aanbiedingen</a><b>Gebruik</b><a href="zonnebrand-lichaam.html">Lichaam</a><a href="zonnebrand-gezicht.html">Gezicht</a><a href="zonnebrand-kinderen.html">Kinderen</a><a href="zonnebrand-wintersport.html">Wintersport</a><b>Productsoort</b><a href="zonnebrandcreme-lotion.html">Crème & lotion</a><a href="zonnebrandspray.html">Spray</a><a href="zonnebrandfluid.html">Fluid</a><a href="zonnebrandstick.html">Stick</a><a href="zonnebrandolie.html">Olie</a><a href="vragen.html">Zonnebrandvragen</a></div></details>`;
  header.appendChild(nav);
  document.addEventListener('click', event => {
    if (!nav.contains(event.target)) nav.querySelectorAll('details').forEach(item => item.open = false);
  });
})();
