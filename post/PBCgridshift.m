function [Vp,varargout] = PBCgridshift(varargin)
%PBCGRIDSHIFT shift meshgrid/ndgrid meshed values to a vector P assuming periodic boundary conditions
%             and considering the grid created by either meshgrid or ndgrid.
%
%   USAGE in 3D
%       [Vp,Xp,Yp,Zp] = PBCgrid(X,Y,Z,V,P)
%   USAGE in 2D
%       [Vp,Xp,Yp] = PBCgrid(X,Y,V,P)
%   USAGE in 1D
%       [Vp,Xp] = PBCgrid(X,V,P)
%
%   INPUTS (3D):
%            X: a x b x c array created by meshgrid, ndgrid coding for X coordinates
%            Y: a x b x c array created by meshgrid, ndgrid coding for Y coordinates
%            Z: a x b x c array created by meshgrid, ndgrid coding for Z coordinates
%            V: a x b x c array where V(i,j,k) is the value at X(i,j,k), Y(i,j,k) and Z(i,j,k)
%            P: 3 x 1 shift vector (units in grid step)
%               P(1) is the shift along x, P(2) along y, P(3) along z
%
%   INPUTS (2D):
%            X: a x b array created by meshgrid, ndgrid coding for X coordinates
%            Y: a x b array created by meshgrid, ndgrid coding for Y coordinates
%            V: a x b array where V(i,j) is the value at X(i,j) and Y(i,j)
%            P: 2 x 1 shift vector (units in grid step)
%               P(1) is the shift along x, P(2) along y
%
%   INPUTS (1D):
%            X: a x 1 array created by linspace or equivalent
%            V: a x 1 array where V(i) is the value at X(i)
%            P: scalar shift (units in grid step)
%
%   OUTPUTS (1-3D)
%           Vp: array of the same size as V
%           Xp,Yp,Zp corresponding coordinates (with proper translation)
%           preserving the nature of the grid (ndgrid or meshgrid)
%
%
%   Note1: an error is returned if X,Y,Z are not generated by meshgrid or ndgrid
%   Note2: This function assumes a uniform grid
%
%
%
%   See also: PBCgrid, PBCimages, PBCimageschift, PBCincell
%
%
% Example:
%      [X,Y,V] = peaks(100);
%      [Vp,Xp,Yp] = PBCgridshift(X,Y,V,[10 20]);
%      figure, mesh(Xp,Yp,Vp)



% MS 3.0 | 2024-03-24 | INRAE\han.chen@inrae.fr, INRAE\Olivier.vitrac@agroparistech.fr | rev.


% Revision history



% Determine the number of dimensions and validate input
X = varargin{1};
d = ndims(X); %<<- the number of dimensions in X sets 1D, 2D or 3D syntax
if d>3, error('the number of dimensions should be 1,2,3'), end
if d==3 && nargin<5, error('five arguments are at least required in 3D:  [Vp,Xp,Yp,Zp] = PBCgridshift(X,Y,Z,V,P)'), end
if d==2 && nargin<4, error('four arguments are at least required in 2D:  [Vp,Xp,Yp] = PBCgridshift(X,Y,V,P)'), end
if d>1
    Y = varargin{2};
    if ~isequal(size(X),size(Y)), error('X and Y are not compatible'), end
    if d>2 % 3D
        Z = varargin{3};
        if ~isequal(size(X),size(Z)), error('X, Y and Z are not compatible'), end
        V = varargin{4};
        if ~isequal(size(X),size(V)), error('V is not compatible with supplied X, Y and Z'), end
        P = varargin{5};
        if nargin>5, error('4 arguments in 3D'), end
        deltaZ = Z(1,1,2) - Z(1,1,1);
    else % 2D
        V = varargin{3};
        if ~isequal(size(X),size(V)), error('V is not compatible with supplied X and Y'), end
        P = varargin{4};
        if nargin>4, error('4 arguments in 2D'), end
    end
    isMesh = X(1,1,:) == X(2,1,:);
    if isMesh
        deltaX = X(1,2,1) - X(1,1,1);
        deltaY = Y(2,1,1) - Y(1,1,1);
    else % ndgrid
        deltaX = X(2,1,1) - X(1,1,1);
        deltaY = Y(1,2,1) - Y(1,1,1);
    end
else % 1D
    V = varargin{2};
    if ~isequal(size(X),size(V)), error('V is not compatible with supplied X'), end
    P = varargin{3};
    if nargin>3, error('3 arguments in 2D'), end
    isMesh = false; % 1D grid doesn't require meshgrid/ndgrid distinction
    deltaX = X(2)-X(1);
end


% Translate Xp,Yp,Zp
varargout{1} = X + P(1) * deltaX;
if d>1,  varargout{2} = Y + P(2) * deltaY; end
if d==3, varargout{3} = Z + P(3) * deltaZ; end

% Apply periodic boundary condition shift based on the dimensionality
switch d
    case 1
        shift = mod((0:numel(X)-1) + P(1), numel(X)) + 1;
        Vp = V(shift);

    case 2
        [rows, cols] = size(X);
        if isMesh
            rShift = mod((0:rows-1)' + P(2), rows) + 1;
            cShift = mod((0:cols-1) + P(1), cols) + 1;
            Vp = V(rShift, cShift);
        else
            rShift = mod((0:rows-1)' + P(1), rows) + 1;
            cShift = mod((0:cols-1) + P(2), cols) + 1;
            Vp = V(cShift, rShift);
        end

    case 3
        [rows, cols, pages] = size(X);
        zShift = mod((0:pages-1) + P(3), pages) + 1;

        if isMesh
            rShift = mod((0:rows-1)' + P(2), rows) + 1;
            cShift = mod((0:cols-1) + P(1), cols) + 1;
            Vp = V(rShift, cShift, zShift);
        else
            rShift = mod((0:rows-1)' + P(1), rows) + 1;
            cShift = mod((0:cols-1) + P(2), cols) + 1;
            Vp = V(cShift, rShift, zShift);
        end
end
