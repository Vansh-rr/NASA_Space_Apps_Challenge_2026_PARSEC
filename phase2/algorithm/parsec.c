/* PARSEC: one C11 scientific core. No external numerical libraries.
 * Calibrate -> common footprint likelihood -> exact/particle smoothing ->
 * cut-posterior mixture -> posterior field and held-out sensor predictions.
 * Geometry/download/provenance preparation is separate from scientific inference.
 */
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <math.h>
#include <errno.h>
#include <limits.h>
#include <sys/stat.h>
#include <stdarg.h>
#define ID 192
#define PATHLEN 4096
#define PI 3.14159265358979323846
#define MAXK 32
#define CHAINS 4
#define SQ(x) ((x)*(x))
static void fail(const char *s) {
    fprintf(stderr,"ERROR: %s\n",s);
    exit(2);
}
static void check(int ok,const char *s) {
    if(!ok)fail(s);
}
static void *mem(size_t n,size_t s) {
    check(!s||n<=SIZE_MAX/s,"allocation overflow");
    void *p=calloc(n?n:1,s?s:1);
    check(p!=NULL,"out of memory");
    return p;
}
static FILE *openf(const char *p,const char *m) {
    FILE *f=fopen(p,m);
    if(!f) {
        fprintf(stderr,"ERROR: cannot open %s\n",p);
        exit(2);
    }
    return f;
}
static FILE *output(const char *dir,const char *name) {
    char p[PATHLEN];
    check(snprintf(p,sizeof p,"%s/%s",dir,name)<(int)sizeof p,"path too long");
    return openf(p,"w");
}
static void finish(FILE *f) {
    check(!ferror(f),"write failed");
    check(fclose(f)==0,"close failed");
}
static void newdir(const char *p) {
    check(mkdir(p,0755)==0,"output directory must be new; create parent first");
}
static void token(FILE *f,char *s) {
    check(fscanf(f,"%191s",s)==1,"missing input token");
    check(strlen(s)<ID-1,"token too long");
}
static void expect(FILE *f,const char *s) {
    char b[ID];
    token(f,b);
    check(!strcmp(b,s),"unexpected input header");
}
static double number(const char *s) {
    char *end;
    errno=0;
    double x=strtod(s,&end);
    check(end!=s&&!*end&&!errno&&isfinite(x),"invalid numeric input");
    return x;
}
static double num(FILE *f) {
    char s[ID];
    token(f,s);
    return number(s);
}
static int integer(double x,int lo,int hi) {
    check(x>=lo&&x<=hi&&x==floor(x),"integer outside permitted range");
    return (int)x;
}
static int inum(FILE *f,int lo,int hi) {
    return integer(num(f),lo,hi);
}
static void eof(FILE *f) {
    char b[ID];
    check(fscanf(f,"%191s",b)==EOF&&!ferror(f),"unexpected trailing input");
    fclose(f);
}
static void ident(const char *s) {
    check(*s&&strspn(s,"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-.:+") == strlen(s),"invalid identifier (use letters/digits/_-.:+)");
}
static void readid(FILE *f,char *s) {
    token(f,s);
    ident(s);
}
static int cmpid(const void*a,const void*b) {
    return strcmp(a,b);
}
static void unique(char (*ids)[ID],int n) {
    qsort(ids,n,ID,cmpid);
    for(int i=1;i<n;i++)check(strcmp(ids[i-1],ids[i]),"duplicate identifier");
}
static uint64_t rng_state;
static uint64_t rng64(void) {
    uint64_t z=(rng_state+=UINT64_C(0x9e3779b97f4a7c15));
    z=(z^(z>>30))*UINT64_C(0xbf58476d1ce4e5b9);
    z=(z^(z>>27))*UINT64_C(0x94d049bb133111eb);
    return z^(z>>31);
}
static double U(void) {
    return ((double)(rng64()>>12)+0.5)*0x1p-52;
}
static double normal(void) {
    return sqrt(-2*log(U()))*cos(2*PI*U());
}
static double gamma_draw(double a) {
    if(a<1)return gamma_draw(a+1)*pow(U(),1/a);
    double d=a-1./3,c=1/sqrt(9*d);
    for(;;) {
        double x=normal(),v=1+c*x;
        if(v<=0)continue;
        v=v*v*v;
        double u=U();
        if(u<1-.0331*x*x*x*x||log(u)<.5*x*x+d*(1-v+log(v)))return d*v;
    }
}
static double logistic(double x) {
    if(x>=0)return 1/(1+exp(-x));
    double e=exp(x);
    return e/(1+e);
}
static double clip(double x) {
    return fmax(1e-15,fmin(1-1e-15,x));
}
static double bern(int d,double p) {
    p=clip(p);
    return d?log(p):log1p(-p);
}
static double logbern(int d,double x) {
    double a=d?-x:x;
    return -fmax(a,0)-log1p(exp(-fabs(a)));
}
static double lognormal_density(double r,double mu,double sd) {
    return -.5*SQ((log(r)-mu)/sd)-log(sd)-log(r)-.5*log(2*PI);
}
static double normalize(double *p,int n) {
    double m=-INFINITY,z=0;
    for(int i=0;i<n;i++)m=fmax(m,p[i]);
    check(isfinite(m),"nonfinite likelihood");
    for(int i=0;i<n;i++) {
        p[i]=exp(p[i]-m);
        z+=p[i];
    }
    check(z>0&&isfinite(z),"invalid normalization");
    for(int i=0;i<n;i++)p[i]/=z;
    return m+log(z);
}
static int categorical(const double *p,int n) {
    double u=U(),c=0;
    for(int i=0;i<n-1;i++) {
        c+=p[i];
        if(u<c)return i;
    }
    return n-1;
}
static double ess(const double*w,int n) {
    double z=0;
    for(int i=0;i<n;i++)z+=w[i]*w[i];
    return 1/z;
}
static int cmpnum(const void*a,const void*b) {
    double x=*(const double*)a,y=*(const double*)b;
    return (x>y)-(x<y);
}
/* 1. Bayesian calibration, with the same collapsed FRP model and priors as
 * the earlier implementation. Four independent chains, genuine joint draws. */
typedef struct {
    double n,m,v,mm,vv,mv;
}
Sufficient;
typedef struct {
    double mu,b,t,sm,sv;
}
Frp;
typedef struct {
    double a,b,f,bias,sd,fmu,fsd;
}
Sensor;
typedef struct {
    Sensor s[2];
}
Params;
typedef struct {
    int n,fp,tn;
    double *h;
    int *d;
}
Labels;
typedef struct {
    char kind[ID];
    int count,ng;
    char (*groups)[ID];
    Params *draws;
}
Calibration;
static Params defaults(void) {
    return (Params) {
        {
            {
                -1.5,.5,.01,0,.32,1,.8
            }, {
                -.8,.7,.005,0,.2,1,.8
            }
        }
    };
}
static void check_params(Params p) {
    for(int s=0;s<2;s++) {
        Sensor a=p.s[s];
        check(isfinite(a.a)&&isfinite(a.b)&&isfinite(a.f)&&isfinite(a.bias)&&isfinite(a.sd)&&isfinite(a.fmu)&&isfinite(a.fsd)&&a.b>=0&&a.f>0&&a.f<1&&a.sd>0&&a.fsd>0,"invalid observation parameters");
    }
}
static double frp_loglik(Frp p,Sufficient a) {
    double t=SQ(p.t),m=SQ(p.sm),v=SQ(p.sv),det=t*(m+v)+m*v;
    if(!(det>0&&isfinite(det)))return -INFINITY;
    double x=p.mu+p.b,y=p.mu;
    double mm=a.mm-2*x*a.m+a.n*x*x,vv=a.vv-2*y*a.v+a.n*y*y,mv=a.mv-x*a.v-y*a.m+a.n*x*y;
    return -.5*a.n*log(det)-.5*fmax(0,((t+v)*mm+(t+m)*vv-2*t*mv)/det);
}
typedef double (*LogDensity)(double,void*);
static double slice(double x,LogDensity fun,void *ctx,double width) {
    double y=fun(x,ctx)+log(U());
    check(isfinite(y),"invalid slice start");
    double l=x-width*U(),r=l+width;
    int j=(int)(U()*35),k=34-j;
    while(j-->0&&fun(l,ctx)>y)l-=width;
    while(k-->0&&fun(r,ctx)>y)r+=width;
    for(int i=0;i<1000;i++) {
        double u=l+(r-l)*U();
        if(fun(u,ctx)>=y)return u;
        if(u<x)l=u;
        else r=u;
    }
    fail("slice sampler failed");
    return 0;
}
typedef struct {
    Frp p;
    Sufficient a;
    int which;
}
FrpCtx;
static double hyper(double u,void *ctx) {
    FrpCtx *c=ctx;
    if(u< -12||u>5)return -INFINITY;
    Frp p=c->p;
    double s=exp(u);
    if(c->which==0)p.sm=s;
    else if(c->which==1)p.sv=s;
    else p.t=s;
    return frp_loglik(p,c->a)-.5*SQ(s/(c->which==2?2:1))+u;
}
static void sweep(Frp *p,Sufficient a) {
    double t=SQ(p->t),m=SQ(p->sm),v=SQ(p->sv),det=t*(m+v)+m*v;
    double p00=1./9+a.n*(m+v)/det,p01=a.n*v/det,p11=1./SQ(.8)+a.n*(t+v)/det;
    double r0=log(30.)/9+(v*a.m+m*a.v)/det,r1=((t+v)*a.m-t*a.v)/det,d=p00*p11-p01*p01;
    check(d>0,"invalid calibration precision");
    double vm=p11/d,vb=p00/d,c=-p01/d,z=normal();
    p->mu=(p11*r0-p01*r1)/d+sqrt(vm)*z;
    p->b=(-p01*r0+p00*r1)/d+c/sqrt(vm)*z+sqrt(fmax(0,vb-c*c/vm))*normal();
    for(int j=0;j<3;j++) {
        FrpCtx q= {
            *p,a,j
        };
        double x=exp(slice(log(j==0?p->sm:j==1?p->sv:p->t),hyper,&q,.35));
        if(j==0)p->sm=x;
        else if(j==1)p->sv=x;
        else p->t=x;
    }
}
typedef struct {
    Labels *d;
    double center,log_slope;
    int which;
}
DetCtx;
static double det_density(double x,void *ctx) {
    DetCtx *c=ctx;
    double a=c->which?c->center:x,k=c->which?x:c->log_slope;
    if(fabs(k)>25)return -INFINITY;
    double b=exp(k),v=-.5*SQ(a/2)-.5*SQ((k-log(.6))/.8);
    for(int i=0;i<c->d->n;i++)v+=logbern(c->d->d[i],a+b*(c->d->h[i]-3));
    return v;
}
static Sensor det_sweep(DetCtx *c,int s) {
    c->which=0;
    c->center=slice(c->center,det_density,c,.75);
    c->which=1;
    c->log_slope=slice(c->log_slope,det_density,c,.45);
    double b=exp(c->log_slope),x=gamma_draw(1+c->d->fp),y=gamma_draw((s?199:99)+c->d->tn);
    Sensor q=defaults().s[s];
    q.a=c->center-3*b;
    q.b=b;
    q.f=x/(x+y);
    return q;
}
static void addgroup(Calibration *c,const char *g) {
    for(int i=0;i<c->ng;i++)if(!strcmp(c->groups[i],g))return;
    check(c->ng<10000,"too many calibration groups");
    strcpy(c->groups[c->ng++],g);
}
static int read_kind(FILE*f,char*k) {
    token(f,k);
    check(!strcmp(k,"SYNTHETIC")||!strcmp(k,"REAL_REVIEWED"),"calibration source must be SYNTHETIC or REAL_REVIEWED");
    return !strcmp(k,"REAL_REVIEWED");
}
static Sufficient read_pairs(const char *path,Calibration*c) {
    FILE*f=openf(path,"r");
    expect(f,"PAIRS1");
    read_kind(f,c->kind);
    int n=inum(f,30,2000000);
    Sufficient a= {
        0
    };
    char g[ID];
    for(int i=0;i<n;i++) {
        readid(f,g);
        addgroup(c,g);
        double m=num(f),v=num(f);
        check(m>0&&v>0,"calibration FRP must be positive");
        m=log(m);
        v=log(v);
        a.n++;
        a.m+=m;
        a.v+=v;
        a.mm+=m*m;
        a.vv+=v*v;
        a.mv+=m*v;
    }
    eof(f);
    return a;
}
static void read_labels(const char*path,Calibration*c,Labels*l) {
    FILE*f=openf(path,"r");
    expect(f,"LABELS1");
    char kind[ID],g[ID];
    read_kind(f,kind);
    check(!strcmp(kind,c->kind),"mixed calibration provenance");
    int n=inum(f,1,2000000);
    for(int s=0;s<2;s++) {
        l[s].h=mem(n,sizeof(double));
        l[s].d=mem(n,sizeof(int));
    }
    for(int i=0;i<n;i++) {
        readid(f,g);
        addgroup(c,g);
        int s=inum(f,0,1),z=inum(f,0,1);
        double r=num(f);
        int usable=inum(f,0,1),d=inum(f,-1,1);
        check((z&&r>0)||(!z&&r==0),"reference FRP inconsistent with fire label");
        check(usable?d>=0:d==-1,"unavailable labels must have detection -1");
        if(!usable)continue;
        if(z) {
            l[s].h[l[s].n]=log(r);
            l[s].d[l[s].n++]=d;
        }else if(d)l[s].fp++;
        else l[s].tn++;
    }
    eof(f);
    for(int s=0;s<2;s++)check(l[s].n>=30&&l[s].fp+l[s].tn>=30,"need at least 30 usable fire and nonfire references per sensor");
}
static void emit_params(FILE*f,const Params*p) {
    for(int s=0;s<2;s++) {
        Sensor q=p->s[s];
        fprintf(f,"%.17g %.17g %.17g %.17g %.17g %.17g %.17g%s",q.a,q.b,q.f,q.bias,q.sd,q.fmu,q.fsd,s?"\n":" ");
    }
}
static Calibration load_params(const char*path) {
    Calibration c= {
        0
    };
    if(!strcmp(path,"illustrative")) {
        strcpy(c.kind,"ILLUSTRATIVE");
        c.count=1;
        c.draws=mem(1,sizeof(Params));
        c.draws[0]=defaults();
        return c;
    }
    FILE*f=openf(path,"r");
    expect(f,"PARSEC_PARAMS1");
    read_kind(f,c.kind);
    c.count=inum(f,1,200000);
    c.ng=inum(f,1,10000);
    c.groups=mem(c.ng,ID);
    for(int i=0;i<c.ng;i++)readid(f,c.groups[i]);
    unique(c.groups,c.ng);
    c.draws=mem(c.count,sizeof(Params));
    for(int i=0;i<c.count;i++) {
        for(int s=0;s<2;s++) {
            Sensor*q=&c.draws[i].s[s];
            q->a=num(f);
            q->b=num(f);
            q->f=num(f);
            q->bias=num(f);
            q->sd=num(f);
            q->fmu=num(f);
            q->fsd=num(f);
        }
        check_params(c.draws[i]);
    }
    eof(f);
    return c;
}
/* Classical split R-hat and initial-positive autocorrelation ESS (approximate). */
static int diagnostics(FILE*f,const char*name,const double*x,int n) {
    int h=n/2,m=2*CHAINS;
    double means[2*CHAINS],W=0,grand=0;
    double *copy=mem((size_t)n*CHAINS,sizeof(double));
    memcpy(copy,x,(size_t)n*CHAINS*sizeof(double));
    for(int c=0;c<m;c++) {
        const double*a=x+(c/2)*n+(c%2?n-h:0);
        double mu=0,v=0;
        for(int i=0;i<h;i++)mu+=a[i]/h;
        for(int i=0;i<h;i++)v+=SQ(a[i]-mu);
        means[c]=mu;
        grand+=mu/m;
        W+=v/(h-1)/m;
    }
    double B=0;
    for(int c=0;c<m;c++)B+=h*SQ(means[c]-grand)/(m-1);
    double rhat=W>0?sqrt(((h-1.)*W+B)/(h*W)):INFINITY;
    double rho_sum=0,previous=0;
    for(int lag=1;lag<h/2;lag++) {
        double ac=0;
        for(int c=0;c<m;c++) {
            const double*a=x+(c/2)*n+(c%2?n-h:0);
            for(int i=0;i<h-lag;i++)ac+=(a[i]-means[c])*(a[i+lag]-means[c])/(m*(double)(h-lag));
        }
        double rho=W>0?ac/W:0;
        if(lag%2)previous=rho;
        else {
            if(previous+rho<=0)break;
            rho_sum+=previous+rho;
        }
    }
    double e=m*h/(1+2*fmax(0,rho_sum));
    qsort(copy,(size_t)n*CHAINS,sizeof(double),cmpnum);
    int ok=isfinite(rhat)&&rhat<=1.05&&e>=100;
    fprintf(f,"%s,%.9g,%.9g,%.9g,%.9g,%.9g,%s\n",name,grand,copy[(int)(.025*(n*CHAINS-1))],copy[(int)(.975*(n*CHAINS-1))],rhat,e,ok?"OK":"WARNING");
    free(copy);
    return ok;
}
static void calibrate(const char*pairs,const char*labels,const char*out,int warm,int draws,uint64_t seed,int reviewed) {
    Calibration c= {
        0
    };
    c.groups=mem(10000,ID);
    Sufficient a=read_pairs(pairs,&c);
    Labels l[2]= {
        {
            0
        }
    };
    read_labels(labels,&c,l);
    check(strcmp(c.kind,"REAL_REVIEWED")||reviewed,"real calibration needs explicit review acknowledgement");
    int n=CHAINS*draws;
    c.count=n;
    c.draws=mem(n,sizeof(Params));
    double *series=mem((size_t)11*n,sizeof(double));
    newdir(out);
    FILE*joint=output(out,"calibration_draws.csv");
    fprintf(joint,"chain,draw,mu,tau,modis_bias,modis_sd,viirs_sd,modis_alpha,modis_beta,modis_far,viirs_alpha,viirs_beta,viirs_far\n");
    rng_state=seed;
    for(int ch=0;ch<CHAINS;ch++) {
        Frp f= {
            a.v/a.n+.1*normal(),(a.m-a.v)/a.n+.1*normal(),.7+.1*ch,.25+.05*ch,.15+.05*ch
        };
        DetCtx dc[2]= {
            {
                &l[0],-.4+.3*ch,log(.35+.12*ch),0
            }, {
                &l[1],-.4+.3*ch,log(.35+.12*ch),0
            }
        };
        for(int j=0;j<warm+draws;j++) {
            sweep(&f,a);
            Params p=defaults();
            for(int s=0;s<2;s++)p.s[s]=det_sweep(&dc[s],s);
            p.s[0].bias=f.b;
            p.s[0].sd=f.sm;
            p.s[1].sd=f.sv;
            if(j>=warm) {
                int i=ch*draws+j-warm;
                c.draws[i]=p;
                double v[]= {
                    f.mu,f.t,f.b,f.sm,f.sv,p.s[0].a,p.s[0].b,p.s[0].f,p.s[1].a,p.s[1].b,p.s[1].f
                };
                fprintf(joint,"%d,%d",ch+1,j-warm+1);
                for(int k=0;k<11;k++) {
                    series[k*n+i]=v[k];
                    fprintf(joint,",%.17g",v[k]);
                }
                fputc('\n',joint);
            }
        }
        printf("Calibration chain %d/%d completed\n",ch+1,CHAINS);
        fflush(stdout);
    }
    finish(joint);
    const char*names[]= {
        "mu","tau","modis_bias","modis_sd","viirs_sd","modis_alpha","modis_beta","modis_far","viirs_alpha","viirs_beta","viirs_far"
    };
    FILE*d=output(out,"calibration_summary.csv");
    fprintf(d,"parameter,mean,ci95_low,ci95_high,split_rhat,approx_ess,status\n");
    int ok=1;
    for(int k=0;k<11;k++)ok&=diagnostics(d,names[k],series+k*n,draws);
    finish(d);
    check(ok,"calibration diagnostics failed; no usable params.txt exported");
    FILE*f=output(out,"params.txt");
    fprintf(f,"PARSEC_PARAMS1 %s %d %d\n",c.kind,c.count,c.ng);
    for(int i=0;i<c.ng;i++)fprintf(f,"%s\n",c.groups[i]);
    for(int i=0;i<c.count;i++)emit_params(f,&c.draws[i]);
    finish(f);
    printf("PASS: calibration (%s); %d joint modular draws\n",c.kind,c.count);
    free(series);
    free(c.draws);
    free(c.groups);
    for(int s=0;s<2;s++) {
        free(l[s].h);
        free(l[s].d);
    }
}
/* 2. Common latent field, sparse footprint operators and single sensor likelihood. */
typedef struct {
    char id[ID],group[ID];
    int t,s,c,d,hold,nw;
    double r;
    int *idx;
    double *w;
}
Obs;
typedef struct {
    char kind[ID];
    int n,T,K,M,E;
    double levels[MAXK],prior,persistence,neighbor,mu,sd;
    char (*cells)[ID],(*times)[ID];
    int *degree,**adj;
    Obs*obs;
    int *start,*order;
}
Data;
static int byid(const void*a,const void*b) {
    return strcmp(((const Obs*)a)->id,((const Obs*)b)->id);
}
static int bygroup(const void*a,const void*b) {
    return strcmp(((const Obs*)a)->group,((const Obs*)b)->group);
}
static Data load_data(const char*path) {
    Data a= {
        0
    };
    FILE*f=openf(path,"r");
    expect(f,"PARSEC_FIELD1");
    token(f,a.kind);
    check(!strcmp(a.kind,"SYNTHETIC")||!strcmp(a.kind,"REAL_REVIEWED")||!strcmp(a.kind,"NASA_MASK_EXPLORATORY"),"unknown input source kind");
    a.n=inum(f,1,3000);
    a.T=inum(f,1,500);
    a.K=inum(f,2,MAXK);
    a.M=inum(f,1,200000);
    a.E=inum(f,0,1000000);
    for(int k=0;k<a.K;k++) {
        a.levels[k]=num(f);
        check((k?a.levels[k]>a.levels[k-1]:a.levels[k]==0)&&a.levels[k]<=1e12,"FRP levels must increase from zero and be <=1e12 MW");
    }
    a.prior=num(f);
    a.persistence=num(f);
    a.neighbor=num(f);
    a.mu=num(f);
    a.sd=num(f);
    check(a.prior>0&&a.prior<1&&a.persistence>=0&&a.neighbor>=0&&a.sd>0,"invalid dynamics");
    a.cells=mem(a.n,ID);
    a.times=mem(a.T,ID);
    for(int i=0;i<a.n;i++)readid(f,a.cells[i]);
    for(int i=0;i<a.T;i++)readid(f,a.times[i]);
    char(*tmp)[ID]=mem(a.n>a.T?a.n:a.T,ID);
    memcpy(tmp,a.cells,a.n*ID);
    unique(tmp,a.n);
    memcpy(tmp,a.times,a.T*ID);
    unique(tmp,a.T);
    free(tmp);
    a.degree=mem(a.n,sizeof(int));
    a.adj=mem(a.n,sizeof(int*));
    int*e1=mem(a.E,sizeof(int)),*e2=mem(a.E,sizeof(int));
    for(int i=0;i<a.E;i++) {
        e1[i]=inum(f,0,a.n-1);
        e2[i]=inum(f,0,a.n-1);
        check(e1[i]<e2[i],"edges must be unique ordered pairs i<j");
        a.degree[e1[i]]++;
        a.degree[e2[i]]++;
    }
    for(int i=0;i<a.n;i++) {
        a.adj[i]=mem(a.degree[i],sizeof(int));
        a.degree[i]=0;
    }
    for(int i=0;i<a.E;i++) {
        int x=e1[i],y=e2[i];
        for(int k=0;k<a.degree[x];k++)check(a.adj[x][k]!=y,"duplicate adjacency edge");
        a.adj[x][a.degree[x]++]=y;
        a.adj[y][a.degree[y]++]=x;
    }
    free(e1);
    free(e2);
    a.obs=mem(a.M,sizeof(Obs));
    int train=0;
    for(int i=0;i<a.M;i++) {
        Obs*o=&a.obs[i];
        readid(f,o->id);
        readid(f,o->group);
        o->t=inum(f,0,a.T-1);
        o->s=inum(f,0,1);
        o->c=inum(f,0,1);
        o->d=inum(f,-1,1);
        o->r=num(f);
        o->hold=inum(f,0,1);
        o->nw=inum(f,1,a.n);
        check((o->c&&o->d>=0)||(!o->c&&o->d==-1&&o->r==-1),"invalid coverage/detection");
        check(o->r==-1||(o->r>0&&o->c&&o->d==1),"FRP must be positive or missing (-1)");
        check(strcmp(a.kind,"NASA_MASK_EXPLORATORY")||o->r==-1,"exploratory NASA masks cannot carry FRP");
        check(strcmp(a.kind,"REAL_REVIEWED")||o->s==0||o->r==-1,"real VIIRS retrieval support not validated; FRP refused");
        o->idx=mem(o->nw,sizeof(int));
        o->w=mem(o->nw,sizeof(double));
        for(int j=0;j<o->nw;j++) {
            o->idx[j]=inum(f,0,a.n-1);
            o->w[j]=num(f);
            check(o->w[j]>0&&o->w[j]<=1,"invalid footprint weight");
            check(j==0||o->idx[j]>o->idx[j-1],"footprint indices must be sorted and unique");
        }
        train+=o->c&&!o->hold;
    }
    eof(f);
    check(train>0,"no usable training observations");
    qsort(a.obs,a.M,sizeof(Obs),bygroup);
    for(int i=1;i<a.M;i++)if(!strcmp(a.obs[i-1].group,a.obs[i].group))check(a.obs[i-1].hold==a.obs[i].hold,"train/holdout observation group overlap");
    qsort(a.obs,a.M,sizeof(Obs),byid);
    for(int i=1;i<a.M;i++)check(strcmp(a.obs[i-1].id,a.obs[i].id),"duplicate observation ID");
    a.start=mem(a.T+1,sizeof(int));
    a.order=mem(a.M,sizeof(int));
    for(int i=0;i<a.M;i++)a.start[a.obs[i].t+1]++;
    for(int t=0;t<a.T;t++)a.start[t+1]+=a.start[t];
    int*at=mem(a.T,sizeof(int));
    memcpy(at,a.start,a.T*sizeof(int));
    for(int i=0;i<a.M;i++)a.order[at[a.obs[i].t]++]=i;
    free(at);
    return a;
}
static void free_data(Data*a) {
    for(int i=0;i<a->M;i++) {
        free(a->obs[i].idx);
        free(a->obs[i].w);
    }
    for(int i=0;i<a->n;i++)free(a->adj[i]);
    free(a->adj);
    free(a->degree);
    free(a->obs);
    free(a->cells);
    free(a->times);
    free(a->start);
    free(a->order);
}
static double detect_prob(Sensor s,double q) {
    return clip(q>0?logistic(s.a+s.b*log(q)):s.f);
}
static double obs_ll(const Obs*o,Params p,double q) {
    if(!o->c)return 0;
    Sensor s=p.s[o->s];
    double v=bern(o->d,detect_prob(s,q));
    if(o->r>0)v+=lognormal_density(o->r,q>0?log(q)+s.bias:s.fmu,q>0?s.sd:s.fsd);
    return v;
}
static double power(const Data*a,const Obs*o,const unsigned char*x) {
    double q=0;
    for(int i=0;i<o->nw;i++)q+=o->w[i]*a->levels[x[o->idx[i]]];
    return q;
}
static void mass(const Data*a,double*m) {
    for(int k=0;k<a->K;k++) {
        double c=k?log(a->levels[k]):a->mu;
        double*row=m+k*a->K;
        row[0]=0;
        for(int j=1;j<a->K;j++)row[j]=-.5*SQ((log(a->levels[j])-c)/a->sd);
        normalize(row+1,a->K-1);
    }
}
static void cell_transition(const Data*a,const double*m,const unsigned char*prev,int g,double*p) {
    int k=prev?prev[g]:0;
    double frac=0;
    if(prev&&a->degree[g]) {
        for(int j=0;j<a->degree[g];j++)frac+=prev[a->adj[g][j]]>0;
        frac/=a->degree[g];
    }
    double pr=prev?logistic(log(a->prior/(1-a->prior))+a->persistence*(k>0)+a->neighbor*frac):a->prior;
    p[0]=1-pr;
    for(int j=1;j<a->K;j++)p[j]=pr*m[k*a->K+j];
}
static int states_count(const Data*a) {
    int n=1;
    for(int i=0;i<a->n;i++) {
        if(n>1024/a->K)return 0;
        n*=a->K;
    }
    return n;
}
typedef struct {
    double *prob,*pred;
    double miness;
    int warning;
    int particles;
    int minanc;
}
Fit;
static Fit alloc_fit(const Data*a) {
    Fit f= {
        0
    };
    f.prob=mem((size_t)a->T*a->n*a->K,sizeof(double));
    f.pred=mem(a->M,sizeof(double));
    f.miness=1;
    f.minanc=INT_MAX;
    return f;
}
static void free_fit(Fit*f) {
    free(f->prob);
    free(f->pred);
}
static void accumulate(const Data*a,Params p,Fit*f,int t,const unsigned char*states,const double*w,int N,const int*indices) {
    for(int j=0;j<N;j++) {
        const unsigned char*x=states+(size_t)(indices?indices[j]:j)*a->n;
        double z=w[j];
        for(int g=0;g<a->n;g++)f->prob[((size_t)t*a->n+g)*a->K+x[g]]+=z;
        for(int i=a->start[t];i<a->start[t+1];i++) {
            int k=a->order[i];
            const Obs*o=&a->obs[k];
            if(o->hold&&o->c)f->pred[k]+=z*detect_prob(p.s[o->s],power(a,o,x));
        }
    }
}
/* 3. Exact forward/backward HMM. Emissions scaled per time for stability. */
static Fit exact(const Data*a,Params p) {
    int N=states_count(a);
    check(N>0,"exact solver limited to 1024 joint states");
    Fit f=alloc_fit(a);
    unsigned char*x=mem((size_t)N*a->n,1);
    double *P=mem((size_t)N*N,sizeof(double)),*ini=mem(N,sizeof(double)),*L=mem((size_t)a->T*N,sizeof(double)),*forward=mem((size_t)a->T*N,sizeof(double)),*b=mem(N,sizeof(double)),*next=mem(N,sizeof(double)),*w=mem(N,sizeof(double)),*ct=mem((size_t)a->n*a->K,sizeof(double));
    double m[MAXK*MAXK]= {
        0
    };
    mass(a,m);
    for(int i=0;i<N;i++) {
        int k=i;
        for(int g=a->n-1;g>=0;g--) {
            x[(size_t)i*a->n+g]=(unsigned char)(k%a->K);
            k/=a->K;
        }
    }
    for(int g=0;g<a->n;g++)cell_transition(a,m,NULL,g,ct+g*a->K);
    for(int i=0;i<N;i++) {
        ini[i]=1;
        for(int g=0;g<a->n;g++)ini[i]*=ct[g*a->K+x[(size_t)i*a->n+g]];
    }
    for(int i=0;i<N;i++) {
        for(int g=0;g<a->n;g++)cell_transition(a,m,x+(size_t)i*a->n,g,ct+g*a->K);
        for(int j=0;j<N;j++) {
            double q=1;
            for(int g=0;g<a->n;g++)q*=ct[g*a->K+x[(size_t)j*a->n+g]];
            P[(size_t)i*N+j]=q;
        }
    }
    for(int t=0;t<a->T;t++) {
        double*ll=L+(size_t)t*N;
        for(int i=0;i<N;i++) {
            for(int j=a->start[t];j<a->start[t+1];j++) {
                const Obs*o=&a->obs[a->order[j]];
                if(!o->hold&&o->c)ll[i]+=obs_ll(o,p,power(a,o,x+(size_t)i*a->n));
            }
        }
        normalize(ll,N);
        double*ff=forward+(size_t)t*N;
        double z=0;
        for(int i=0;i<N;i++) {
            double pr=ini[i];
            if(t) {
                pr=0;
                for(int j=0;j<N;j++)pr+=forward[(size_t)(t-1)*N+j]*P[(size_t)j*N+i];
            }
            ff[i]=pr*ll[i];
            z+=ff[i];
        }
        check(z>0&&isfinite(z),"exact forward underflow");
        for(int i=0;i<N;i++)ff[i]/=z;
    }
    for(int i=0;i<N;i++) {
        b[i]=1;
    }
    for(int t=a->T-1;t>=0;t--) {
        double z=0;
        for(int i=0;i<N;i++) {
            w[i]=forward[(size_t)t*N+i]*b[i];
            z+=w[i];
        }
        check(z>0&&isfinite(z),"exact backward underflow");
        for(int i=0;i<N;i++)w[i]/=z;
        accumulate(a,p,&f,t,x,w,N,NULL);
        if(t) {
            double max=0;
            for(int i=0;i<N;i++) {
                next[i]=0;
                for(int j=0;j<N;j++)next[i]+=P[(size_t)i*N+j]*L[(size_t)t*N+j]*b[j];
                max=fmax(max,next[i]);
            }
            check(max>0,"exact backward failure");
            for(int i=0;i<N;i++)b[i]=next[i]/max;
        }
    }
    free(x);
    free(P);
    free(ini);
    free(L);
    free(forward);
    free(b);
    free(next);
    free(w);
    free(ct);
    return f;
}
/* 4. Auxiliary particle filter with locally adapted single-cell proposals.
 * Fixed-lag ancestry smoothing; multi-cell likelihood is applied once. */
static void local_proposal(const Data*a,const double*m,const double*local,const unsigned char*prev,int g,double*p,double*z) {
    cell_transition(a,m,prev,g,p);
    for(int k=0;k<a->K;k++)p[k]=log(p[k])+local[g*a->K+k];
    *z=normalize(p,a->K);
}
static Fit particle(const Data*a,Params p,int N,int lag) {
    check(N>=100&&N<=100000&&lag>=0&&lag<=100,"particle/lag limits");
    int ring=(lag<a->T?lag:a->T-1)+1;
    check((size_t)N*a->n*ring<=48000000 && (size_t)N*a->n*a->K<=60000000,"particle memory guard; reduce grid, lag or particles");
    Fit f=alloc_fit(a);
    f.particles=N;
    unsigned char*hist=mem((size_t)ring*N*a->n,1),*prev=mem((size_t)N*a->n,1);
    int*parents=mem((size_t)ring*N,sizeof(int)),*ancestry=mem(N,sizeof(int)),*seen=mem(N,sizeof(int));
    double*w=mem(N,sizeof(double)),*aux=mem(N,sizeof(double)),*local=mem((size_t)a->n*a->K,sizeof(double));
    double m[MAXK*MAXK]= {
        0
    };
    mass(a,m);
    for(int j=0;j<N;j++)w[j]=1./N;
    for(int t=0;t<a->T;t++) {
        unsigned char*now=hist+(size_t)(t%ring)*N*a->n;
        int*par=parents+(size_t)(t%ring)*N;
        memset(local,0,(size_t)a->n*a->K*sizeof(double));
        for(int i=a->start[t];i<a->start[t+1];i++) {
            const Obs*o=&a->obs[a->order[i]];
            if(o->hold||!o->c||o->nw!=1)continue;
            for(int k=0;k<a->K;k++)local[o->idx[0]*a->K+k]+=obs_ll(o,p,o->w[0]*a->levels[k]);
        }
        if(t) {
            for(int j=0;j<N;j++) {
                double v=log(w[j]);
                for(int g=0;g<a->n;g++) {
                    double q[MAXK],z;
                    local_proposal(a,m,local,prev+(size_t)j*a->n,g,q,&z);
                    v+=z;
                }
                aux[j]=v;
            }
            normalize(aux,N);
            f.miness=fmin(f.miness,ess(aux,N)/N);
            double c=aux[0],u=U()/N;
            int k=0;
            for(int j=0;j<N;j++) {
                double x=u+(double)j/N;
                while(k<N-1&&x>=c)c+=aux[++k];
                par[j]=k;
            }
        }else for(int j=0;j<N;j++)par[j]=j;
        for(int j=0;j<N;j++) {
            const unsigned char*parent=t?prev+(size_t)par[j]*a->n:NULL;
            unsigned char*x=now+(size_t)j*a->n;
            for(int g=0;g<a->n;g++) {
                double q[MAXK],z;
                local_proposal(a,m,local,parent,g,q,&z);
                x[g]=(unsigned char)categorical(q,a->K);
            }
            w[j]=0;
            for(int i=a->start[t];i<a->start[t+1];i++) {
                const Obs*o=&a->obs[a->order[i]];
                if(!o->hold&&o->c&&o->nw>1)w[j]+=obs_ll(o,p,power(a,o,x));
            }
        }
        normalize(w,N);
        f.miness=fmin(f.miness,ess(w,N)/N);
        memcpy(prev,now,(size_t)N*a->n);
        int first=t>=lag?t-lag:0,last=t==a->T-1?t:t-lag;
        if(t<lag&&t!=a->T-1)continue;
        for(int target=first;target<=last;target++) {
            memset(seen,0,N*sizeof(int));
            int count=0;
            for(int j=0;j<N;j++) {
                int idx=j;
                for(int k=t;k>target;k--)idx=parents[(size_t)(k%ring)*N+idx];
                ancestry[j]=idx;
                if(w[j]>0&&!seen[idx]) {
                    seen[idx]=1;
                    count++;
                }
            }
            f.minanc=f.minanc<count?f.minanc:count;
            accumulate(a,p,&f,target,hist+(size_t)(target%ring)*N*a->n,w,N,ancestry);
        }
    }
    f.warning=f.miness<.05||f.minanc<20;
    free(hist);
    free(prev);
    free(parents);
    free(ancestry);
    free(seen);
    free(w);
    free(aux);
    free(local);
    return f;
}
/* 5. Modular uncertainty mixture, cell summaries, held-out sensor prediction.
 * Held-out observations NEVER enter the likelihood. */
static void fit(const char*field,const char*params,const char*out,const char*solver,int N,int J,int lag,uint64_t seed,int reviewed) {
    Data a=load_data(field);
    Calibration c=load_params(params);
    int real=!strcmp(a.kind,"REAL_REVIEWED"),explore=!strcmp(a.kind,"NASA_MASK_EXPLORATORY");
    check(!real||(reviewed&&!strcmp(c.kind,"REAL_REVIEWED")),"reviewed real inference needs reviewed real calibration and acknowledgement");
    check(!explore||!strcmp(c.kind,"ILLUSTRATIVE"),"NASA mask pilot uses explicitly illustrative parameters only");
    check(real||explore||strcmp(c.kind,"REAL_REVIEWED"),"real calibration cannot be silently relabeled synthetic");
    if(real)for(int i=0;i<a.M;i++)if(a.obs[i].hold)check(!bsearch(a.obs[i].group,c.groups,c.ng,ID,cmpid),"calibration/holdout group overlap");
    check(!strcmp(solver,"auto")||!strcmp(solver,"exact")||!strcmp(solver,"particle"),"unknown solver");
    int use_exact=!strcmp(solver,"exact")||(!strcmp(solver,"auto")&&states_count(&a)>0);
    if(!strcmp(c.kind,"ILLUSTRATIVE"))J=1;
    else check(J>=2,"at least two calibration draws required");
    size_t G=(size_t)a.T*a.n,K=a.K;
    check(G*K<=10000000,"posterior output memory guard");
    double *prob=mem(G*K,sizeof(double)),*within=mem(G,sizeof(double)),*mean2=mem(G,sizeof(double)),*pred=mem(a.M,sizeof(double));
    int warning=0,minanc=INT_MAX,maxN=0;
    double miness=1;
    rng_state=seed;
    int *draw_index=mem(J,sizeof(int));
    for(int j=0;j<J;j++)draw_index[j]=(int)(U()*c.count);
    for(int j=0;j<J;j++) {
        Params p=c.draws[draw_index[j]];
        Fit f=use_exact?exact(&a,p):particle(&a,p,N,lag);
        if(!use_exact&&f.warning&&N<=25000) {
            free_fit(&f);
            f=particle(&a,p,N*2,lag);
        }
        warning|=f.warning;
        miness=fmin(miness,f.miness);
        minanc=minanc<f.minanc?minanc:f.minanc;
        maxN=maxN>f.particles?maxN:f.particles;
        for(size_t g=0;g<G;g++) {
            double m=0,v=0;
            for(size_t k=0;k<K;k++) {
                double q=f.prob[g*K+k],x=a.levels[k];
                prob[g*K+k]+=q/J;
                m+=q*x;
                v+=q*x*x;
            }
            within[g]+=fmax(0,v-m*m)/J;
            mean2[g]+=m*m/J;
        }
        for(int i=0;i<a.M;i++)pred[i]+=f.pred[i]/J;
        free_fit(&f);
    }
    newdir(out);
    FILE*f=output(out,"calibration_groups.txt");
    for(int i=0;i<c.ng;i++)fprintf(f,"%s\n",c.groups[i]);
    finish(f);
    f=output(out,"parameters_used.txt");
    fprintf(f,"# %s; columns: MODIS and VIIRS alpha beta false_alarm log_bias log_sd false_frp_log_mean false_frp_log_sd\n",c.kind);
    for(int j=0;j<J;j++)emit_params(f,&c.draws[draw_index[j]]);
    finish(f);
    f=output(out,"field_posterior.csv");
    fprintf(f,"time,cell_id,p_fire,mean_frp_mw,ci95_low_mw,ci95_high_mw,within_variance_mw2,between_variance_mw2,usable_observation_count\n");
    int*support=mem(G,sizeof(int));
    for(int i=0;i<a.M;i++) {
        Obs*o=&a.obs[i];
        if(o->c&&!o->hold)for(int j=0;j<o->nw;j++)support[(size_t)o->t*a.n+o->idx[j]]++;
    }
    for(size_t g=0;g<G;g++) {
        double z=0,m=0,lo=-1,hi=-1;
        for(size_t k=0;k<K;k++) {
            double q=prob[g*K+k];
            check(isfinite(q)&&q>=0,"invalid posterior");
            z+=q;
            m+=q*a.levels[k];
            if(lo<0&&z>=.025)lo=a.levels[k];
            if(hi<0&&z>=.975)hi=a.levels[k];
        }
        check(fabs(z-1)<1e-7&&hi>=lo&&lo>=0,"posterior normalization failure");
        fprintf(f,"%s,%s,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%d\n",a.times[g/a.n],a.cells[g%a.n],fmax(0,fmin(1,1-prob[g*K])),m,lo,hi,within[g],fmax(0,mean2[g]-m*m),support[g]);
    }
    finish(f);
    f=output(out,"posterior_probabilities.csv");
    fprintf(f,"time,cell_id,level_mw,probability\n");
    for(size_t g=0;g<G;g++)for(size_t k=0;k<K;k++)fprintf(f,"%s,%s,%.12g,%.12g\n",a.times[g/a.n],a.cells[g%a.n],a.levels[k],prob[g*K+k]);
    finish(f);
    int train_n[2]= {
        0
    },train_pos[2]= {
        0
    },hold_n[2]= {
        0
    },hold_pos[2]= {
        0
    };
    double bs[2]= {
        0
    },basebs[2]= {
        0
    },ll[2]= {
        0
    },basell[2]= {
        0
    };
    for(int i=0;i<a.M;i++) {
        Obs*o=&a.obs[i];
        if(o->c&&!o->hold) {
            train_n[o->s]++;
            train_pos[o->s]+=o->d;
        }
    }
    f=output(out,"holdout_predictions.csv");
    fprintf(f,"observation_id,group_id,time,sensor,detected,predicted_detection,baseline_detection,baseline_type\n");
    for(int i=0;i<a.M;i++) {
        Obs*o=&a.obs[i];
        if(!o->c||!o->hold)continue;
        int s=o->s;
        double base=train_n[s]?(train_pos[s]+.5)/(train_n[s]+1.):(train_pos[0]+train_pos[1]+.5)/(train_n[0]+train_n[1]+1.);
        double p=clip(pred[i]);
        hold_n[s]++;
        hold_pos[s]+=o->d;
        bs[s]+=SQ(p-o->d);
        basebs[s]+=SQ(base-o->d);
        ll[s]-=bern(o->d,p);
        basell[s]-=bern(o->d,base);
        fprintf(f,"%s,%s,%s,%s,%d,%.12g,%.12g,%s\n",o->id,o->group,a.times[o->t],s?"VIIRS":"MODIS",o->d,p,base,train_n[s]?"same_sensor_train":"pooled_train");
    }
    finish(f);
    f=output(out,"holdout_metrics.csv");
    fprintf(f,"sensor,n,positives,negatives,brier,baseline_brier,logloss,baseline_logloss\n");
    for(int s=0;s<2;s++)if(hold_n[s])fprintf(f,"%s,%d,%d,%d,%.12g,%.12g,%.12g,%.12g\n",s?"VIIRS":"MODIS",hold_n[s],hold_pos[s],hold_n[s]-hold_pos[s],bs[s]/hold_n[s],basebs[s]/hold_n[s],ll[s]/hold_n[s],basell[s]/hold_n[s]);
    finish(f);
    f=output(out,"calibration_draws_used.csv");
    fprintf(f,"draw_index\n");
    for(int j=0;j<J;j++)fprintf(f,"%d\n",draw_index[j]);
    finish(f);
    f=output(out,"report.json");
    fprintf(f,"{\n \"source_kind\":\"%s\",\n \"calibration_kind\":\"%s\",\n \"solver\":\"%s\",\n \"cells\":%d,\n \"time_bins\":%d,\n \"draws\":%d,\n \"particles_max_used\":%d,\n \"minimum_ess_fraction\":%.12g,\n \"minimum_unique_ancestors\":%d,\n \"warning\":%s,\n \"train_modis\":%d,\n \"train_viirs\":%d,\n \"holdout_modis\":%d,\n \"holdout_viirs\":%d,\n \"scientific_status\":\"%s\"\n}\n",a.kind,c.kind,use_exact?"exact":"particle_fixed_lag",a.n,a.T,J,maxN,miness,use_exact?0:minanc,warning?"true":"false",train_n[0],train_n[1],hold_n[0],hold_n[1],explore?"NASA MASK PREDICTIVE AGREEMENT ONLY; ILLUSTRATIVE PARAMETERS; NOT PHYSICAL ACCURACY":real?"REVIEWED INPUT ATTESTATION; independent validation required":"SYNTHETIC ONLY");
    finish(f);
    printf("PASS: inference completed; %s; warning=%s\n",a.kind,warning?"true":"false");
    free(prob);
    free(within);
    free(mean2);
    free(pred);
    free(support);
    free(draw_index);
    free(c.draws);
    free(c.groups);
    free_data(&a);
}
static void help(void) {
    puts("PARSEC unified C11 engine\n  parsec calibrate PAIRS LABELS OUT [warmup=700] [draws=1200] [seed=42] [reviewed]\n  parsec fit FIELD PARAMS OUT [auto|exact|particle] [particles=3000] [draws=16] [lag=3] [seed=42] [reviewed]\n  PARAMS may be 'illustrative' for synthetic or NASA mask-only pilots.\n  Create output parent first; run directory must not exist. See README.md.");
}
int main(int argc,char**argv) {
    if(argc==1||!strcmp(argv[1],"--help")) {
        help();
        return 0;
    }
    if(!strcmp(argv[1],"calibrate")) {
        check(argc>=5&&argc<=9,"calibrate arguments; see --help");
        if(argc==9)check(!strcmp(argv[8],"reviewed"),"expected reviewed acknowledgement");
        calibrate(argv[2],argv[3],argv[4],argc>5?integer(number(argv[5]),100,100000):700,argc>6?integer(number(argv[6]),200,50000):1200,argc>7?(uint64_t)integer(number(argv[7]),0,INT_MAX):42,argc==9);
        return 0;
    }
    if(!strcmp(argv[1],"fit")) {
        check(argc>=5&&argc<=11,"fit arguments; see --help");
        if(argc==11)check(!strcmp(argv[10],"reviewed"),"expected reviewed acknowledgement");
        fit(argv[2],argv[3],argv[4],argc>5?argv[5]:"auto",argc>6?integer(number(argv[6]),100,100000):3000,argc>7?integer(number(argv[7]),1,1000):16,argc>8?integer(number(argv[8]),0,100):3,argc>9?(uint64_t)integer(number(argv[9]),0,INT_MAX):42,argc==11);
        return 0;
    }
    fail("unknown command; see --help");
    return 2;
}

