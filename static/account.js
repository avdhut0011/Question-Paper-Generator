(() => {
  const token=document.querySelector('meta[name="csrf-token"]')?.content;
  if(!token)return;
  const originalFetch=window.fetch.bind(window);
  window.fetch=(resource, options={})=>{
    const target=new URL(resource instanceof Request?resource.url:resource,location.href);
    const method=(options.method||(resource instanceof Request?resource.method:'GET')).toUpperCase();
    if(target.origin===location.origin&&!['GET','HEAD','OPTIONS'].includes(method)){
      options={...options,headers:new Headers(options.headers||(resource instanceof Request?resource.headers:{}))};
      options.headers.set('X-CSRFToken',token);
    }
    return originalFetch(resource,options);
  };
})();
