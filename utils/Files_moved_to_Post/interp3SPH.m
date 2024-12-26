function Vq = interp3SPH(centers,y,Xq,Yq,Zq,W,V)
% INTERP3SPH interpolates y at Xq,Yq,Zq using the 3D kernel W centered on centers
%
%   Syntax:
%       Vq = interp3SPH(X,y,Xq,Yq,Zq [,W,V])
%
%   Inputs:
%     centers : kx3 coordinates of the kernel centers
%           y : kxny values at X (m is the number of values associated with the same center)
%               [] (empty matrix) forces a uniform density calculatoin
%          Xq : array or matrix coordinates along X
%          Yq : array or matrix coordinates along Y
%          Zq : array or matrix coordinates along Z
%           W : kernel function @(r) <-- use kernelSPH() to supply a vectorized kernel
%           V : kx1 volume of the kernels (default=1)
%               [] (empty matrix) or scalar value forces uniform volumes (default =1)
%
%   Output:
,%           Vq : same size as Xq, with an additional dimension if y was an array
%
%   See also: interp2SPH, kernelSPH, packSPH
%
%   Example : interpolate the field x+2*y-3*z
%{
    r = 0.5;
    h = 2*r;
    XYZ = packSPH(5,r);
    W = kernelSPH(h,'lucy',3);
    y = XYZ*[1;2;-3]; % arbitrary field to be interpolated x+2*y-3*z
    nresolution = 50;
    xg = linspace(min(XYZ(:,1))-h,max(XYZ(:,1))+h,nresolution);
    yg = linspace(min(XYZ(:,2))-h,max(XYZ(:,2))+h,nresolution);
    zg = linspace(min(XYZ(:,3))-h,max(XYZ(:,3))+h,nresolution);
    [Xg,Yg,Zg] = meshgrid(xg,yg,zg);
    Vg = interp3SPH(XYZ,y,Xg,Yg,Zg,W);
    figure, hs= slice(Xg,Yg,Zg,Vg,1:3,1:3,[]); set(hs,'edgecolor','none','facealpha',0.5), axis equal
    % comparison with standard scattered interpolation
    F = scatteredInterpolant(XYZ(:,1),XYZ(:,2),XYZ(:,3),y);
    Vg = F(Xg,Yg,Zg);
    figure, hs= slice(Xg,Yg,Zg,Vg,1:3,1:3,[]); set(hs,'edgecolor','none','facealpha',0.5), axis equal
%}
%
% Example : calculate the density between the central bead and its closest neighbor
%{
    r = 0.5;
    h = 2*r;
    XYZ = packSPH(5,r);
    W = kernelSPH(h,'lucy',3);
    [~,icentral] = min(sum((XYZ-mean(XYZ)).^2,2));
    dcentral = sqrt(sum((XYZ-XYZ(icentral,:)).^2,2));
    icontact = find( (dcentral>=2*r-0.0001) & (dcentral<=2*r+0.0001) );
    [~,closest] = min(dcentral(icontact));
    icontact = icontact(closest);
    reducedcurvilinear = linspace(-2.5,2.5,100)';
    curvilinear = reducedcurvilinear*norm(XYZ(icontact,:)-XYZ(icentral,:));
    XYZg = XYZ(icentral,:) + reducedcurvilinear*(XYZ(icontact,:)-XYZ(icentral,:));
    Vg = interp3SPH(XYZ,[],XYZg(:,1),XYZg(:,2),XYZg(:,3),W);
    figure, plot(curvilinear,Vg), xlabel('distance to the central bead'), ylabel('density')
%}

% 2023-02-20 | INRAE\Olivier Vitrac | rev.

% arg check
if nargin<1, centers = []; end
if nargin<2, y = []; end
if nargin<3, Xq = []; end
if nargin<4, Yq = []; end
if nargin<5, Zq = []; end
if nargin<6, W = []; end
if nargin<7, V = []; end
[k,d] = size(centers);
[ky,ny] = size(y);
kv = length(V);
if k==0, error('please supply some centers'), end
if d~=3, error('3 dimensions (columns) are required'), end
if ky*ny==0, y = ones(k,1); ky=k; ny=1; end
if ky~=k, error('the number of y values (%d) does not match the number of kernels (%d)',ky,k), end
if ~isequal(size(Xq),size(Yq)) || ~isequal(size(Yq),size(Zq)), error('Xq,Yq and Zq do not have compatible sizes'), end 
if kv==0, V=1;  kv=1; end
if kv==1, V = ones(k,1)*V; kv=k; end
if kv~=k, error('the number of V values (%d) does not match the number of kernels (%d)',kv,k); end

% main
sumW = cell(1,ny);
verbosity = numel(Xq)>1e4;
for i=1:k
    % initialization if needed
    if i==1
        for iy=1:ny
            sumW{iy} = zeros(size(Xq),class(Xq));
        end
    end
    % interpolation
    if verbosity, dispf('interpolate respectively to kernel %d of %d',i,k); end    
    R = sqrt( (Xq-centers(i,1)).^2 + (Yq-centers(i,2)).^2 + (Zq-centers(i,3)).^2 );
    for iy = 1:ny
        sumW{iy} = sumW{iy} + y(i,iy) * V(i) * W(R);
    end
end

% output
if ny==1
    Vq = sumW{1};
else
    Vq = cat(ndims(Xq)+1,sumW{:});
end
