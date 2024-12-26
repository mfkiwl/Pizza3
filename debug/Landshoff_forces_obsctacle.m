%% Landshoff forces in a wakeflow
% INRAE\Olivier Vitrac - rev. 25/02/2023

% [ SYNOPSIS ] This code simulates the movement of particles in a wake flow,
% in which an obstacle is placed in front of a flow to create a wake downstream.
% The simulation includes particles in several layers, with particles in each
% layer connected by a force that is calculated based on the Landshoff force formula.
% The code uses the SPH (Smoothed Particle Hydrodynamics) method to simulate the motion
% of the particles and the arrows plotted on the particle plot indicate the forces
% between particles. The code also includes a GIF recording function to capture the
% animation of the particle movements and forces.

%% General definitions

% layout definitions and plot customized function
layercolors = struct( ...
    'fixed',rgb('DodgerBlue'),...
    'layer1',rgb('DeepSkyBlue'),...
    'layer2',rgb('Aqua'),...
    'layer3',rgb('PaleTurquoise'),...
    'obstacle',rgb('Crimson') ...
);
layerplot = @(X) viscircles([X.xy],X.R*ones(X.n,1),'color',layercolors.(X.tag));

% configuration functions
layercoord = @(X) transpose([
            linspace(-(X.dx+X.R*2)*(X.n-1)/2,(X.dx+X.R*2)*(X.n-1)/2,X.n)
            ones(1,X.n) * (X.y + X.dy)
            ]);
layersliding = @(X) ones(X.n,1)*X.slidingdirection;
layerredistribute = @(X,x0) x0+[cumsum([0;diff(X.xy(:,1))]+abs(randn(X.n,1))*X.R*0.25)];

% mathematical functions for managing bead displacements
imin = @(d) find(d==min(d),1,'first');
imin2 = @(d) find(d==min(d(d>min(d))),1,'first');
distance = @(xy) sqrt(sum(xy.^2,2));
dist2ref = @(ref,testxy) distance(ref.xy-testxy);
iclosest = @(ref,test) cellfun(@(testxy) imin(dist2ref(ref,testxy)),num2cell(test.xy,2));
iclosest2 = @(ref,test) cellfun(@(testxy) imin2(dist2ref(ref,testxy)),num2cell(test.xy,2));
distance2closest = @(ref,test) distance(ref.xy(iclosest(ref,test),:)-test.xy);
distance2closest2 = @(ref,test) distance(ref.xy(iclosest2(ref,test),:)-test.xy);
contractionfactor = @(ref,test) 1 - ref.R*2*(1-abs(randn(test.n,1)*0.02)) ./ distance2closest(ref,test);
contractionfactor2 = @(ref,test) 1 - ref.R*2*(1-abs(randn(test.n,1)*0.02)) ./ distance2closest(ref,test);
updatexy = @(ref,test) test.xy + (ref.xy(iclosest(ref,test),:)-test.xy) .* contractionfactor(ref,test);
updatexy2 = @(ref,test) test.xy + (ref.xy(iclosest2(ref,test),:)-test.xy) .* contractionfactor2(ref,test);
thermostat = @(v) v .*(1+randn(size(v))*0.04);

% bead size (r) 
r = 0.5;

% Kernel definitions
% The kernel function is used to calculate the smoothing function
% for the SPH method, and the parameters include the smoothing length (h),
% the density (rho), and the coefficients (c0 and q1) used in the Landshoff force calculation.
h = 2 * r;
dWdr = @(r) (r<h) .* (1.0./h.^3.*(r./h-1.0).^3.*-1.5e+1)./pi-(1.0./h.^3.*(r./h-1.0).^2.*((r.*3.0)./h+1.0).*1.5e+1)./pi;
c0 = 10;
q1 = 1;
rho = 1000;

%% Fixed layer
fixed = struct( ...these particles are arbitrarily fixed
    'R',r, ... radius
    'n',32,... number of beads
    'xy',[],... coordinates
    'y',-r,... initial position
    'dx',1e-2,... distance between beads
    'dy',0,...
    'slidingdirection',[1 0],...
    'tag','fixed',...
    'id',0 ...
    );
fixed.xy = layercoord(fixed);
fixed.xy(:,1) = layerredistribute(fixed,0);
fixed.slidingdirection = layersliding(fixed);

%% Layer 1 (in contact with the fixed layer)
layer1 = struct( ...these particles are arbitrarily fixed
    'R',r, ... radius
    'n',16,... number of beads
    'xy',[],... coordinates
    'y',+r,... initial position
    'dx',1e-2,... distance between beads
    'dy',1e-2,...
    'slidingdirection',[1 0],...
    'tag','layer1',...
    'id',1 ...
    );
layer1.xy = layercoord(layer1);
layer1.xy(:,1) = layerredistribute(layer1,fixed.R);
layer1.slidingdirection = layersliding(layer1);


% %% Layer 2 (in contact with the fixed layer)
layer2 = struct( ...these particles are arbitrarily fixed
    'R',r, ... radius
    'n',14,... number of beads
    'xy',[],... coordinates
    'y',+2*r,... initial position
    'dx',1e-2,... distance between beads
    'dy',1e-2,...
    'slidingdirection',[1 0],...
    'tag','layer2',...
    'id',2 ...
    );
layer2.xy = layercoord(layer2);
layer2.xy(:,1) = layerredistribute(layer2,layer1.xy(3,1)-fixed.R);
layer2.slidingdirection = layersliding(layer2);

% %% Layer 3 (in contact with the fixed layer)
layer3 = struct( ...these particles are arbitrarily fixed
    'R',r, ... radius
    'n',12,... number of beads
    'xy',[],... coordinates
    'y',+3*r,... initial position
    'dx',1e-2,... distance between beads
    'dy',1e-2,...
    'slidingdirection',[1 0],...
    'tag','layer3',...
    'id',3 ...
    );
layer3.xy = layercoord(layer3);
layer3.xy(:,1) = layerredistribute(layer3,layer1.xy(4,1));
layer3.slidingdirection = layersliding(layer3);

%% obstacle (in contact with the fixed layer)
[i,j] = meshgrid(-1:1,-1:1); [i,j] = deal(i(:),j(:));
centers = [ 2*i + mod(j,2), sqrt(3)*j ]*r;
centers(sum(centers.^2,2)>1,:)=[];
obstacle = struct( ...these particles are arbitrarily fixed
    'R',r, ... radius
    'n',size(centers,1),... number of beads
    'xy',[
        centers(:,1)+fixed.xy(floor(fixed.n/2),1)+fixed.R*5-min(centers(:,1)), ...
        centers(:,2)+fixed.y+fixed.dy+fixed.R+r-min(centers(:,2))
        ],... coordinates
    'y',+r,... initial position
    'dx',0,... distance between beads
    'dy',0,...
    'slidingdirection',[
         0      1     % SW
         0      1     % W
         0.5    0.5   % NW
         1   -0.2        % SE
         NaN  NaN     % center
         0.5  -0.5    % NE
         0.5  -0.5    % E
         ],...
    'tag','obstacle',...
    'id',100 ...
    );

%% all fixed (for collision only)
allfixed = fixed;
allfixed.xy = [fixed.xy;obstacle.xy];
allfixed.slidingdirection = [fixed.slidingdirection;obstacle.slidingdirection];
allfixed.n = fixed.n + obstacle.n;

%% control (only for validating the design)
clf, axis equal, hold on
layerplot(fixed)
layerplot(layer1)
layerplot(layer2)
layerplot(layer3)
ho=layerplot(obstacle);


%% Dynamic plot

% initial position
v = 4*0.1; % velocity (arbitrary units)
dt = 0.1;
[config1,config2,config3]  = deal(layer1, layer2, layer3);
clf, hold on, axis equal
layerplot(fixed);
ho=layerplot(obstacle);
[hp,ha] = deal([],{});
ax = axis;
axis off
RECORD = false; % set it to true to record a video

% The code then enters a loop that simulates the movement of the particles over time.
for it=1:800
    % layer2 neighbor
    ineigh12 = iclosest(config1,config2);
    ineigh13 = iclosest(config1,config3);
    % move of layer 1
    vshift1 = thermostat(v * allfixed.slidingdirection(iclosest(allfixed,config1),:));
    vshift1 = distance(v)*vshift1./distance(vshift1);
    shift1 = dt * vshift1;
    lastxy1 = config1.xy;
    config1.xy = config1.xy + shift1;
    alternativexy = updatexy2(allfixed,config1); % only alternative point
    config1.xy = updatexy(allfixed,config1);
    realdisplacement1 = distance(config1.xy-lastxy1);
    istuck1 = realdisplacement1<0.01;
    if any(istuck1)
        config1.xy(istuck1,:) = alternativexy(istuck1,:);
    end
    % move of layer 2
    directionlayer1 = config1.xy-lastxy1./distance(config1.xy-lastxy1);
    vshift2 = thermostat(v * directionlayer1(iclosest(layer1,config2),:));
    shift1update = thermostat(config1.xy-lastxy1);
    shift2 = shift1update(ineigh12,:);
    vshift2 = shift2/dt;
    config2.xy = config2.xy + shift2;
    config2.xy = updatexy(config1,config2);

    % move of layer 3
    vshift3 = thermostat(v * directionlayer1(iclosest(layer1,config3),:));
    shift3 = shift1update(ineigh13,:);
    vshift3 = shift3/dt;
    config3.xy = config3.xy + shift3;
    config3.xy = updatexy(config2,config3);


    %The Landshoff forces are then calculated using a nested loop that iterates
    % over all pairs of particles in both layers. The forces are calculated using
    % the kernel function and the Landshoff force formula, which includes the velocity
    % difference and distance between particles, as well as the SPH parameters
    id = [ allfixed.id * ones(allfixed.n,1); config1.id * ones(config1.n,1); config2.id * ones(config2.n,1); config3.id * ones(config3.n,1)];
    xy = [allfixed.xy; config1.xy; config2.xy; config3.xy];
    vxy = [repmat([0 0],allfixed.n,1); vshift1; vshift2; vshift3];
    n = allfixed.n + config1.n + config2.n + + config3.n;
    [mu,nu] = deal(zeros(n,n));
    F = zeros(n,n,2);
    for i = 1:n
        for j = 1:n
            rij = xy(i,:)-xy(j,:);
            vij = vxy(i,:)-vxy(j,:);
            if dot(rij,vij)<0
                mu(i,j) = h * dot(rij,vij)/(dot(rij,rij)+0.01*h^2);
                nu(i,j) = (1/rho) * (-q1*c0*mu(i,j));
                rij_d = norm(rij);
                rij_n = rij/rij_d;
                F(i,j,:) = -nu(i,j)*dWdr(rij_d) * permute(rij_n,[1 3 2]);
            end
        end
    end
    Fbalance = squeeze(sum(F,2));
    f = sum(Fbalance.^2,2);
    flog = log(1+f);
    flogmedian = median(flog(flog>0));
    flogmin = flogmedian/100;
    flogscale = 2*r/flogmedian;
    
    %Finally, the forces are plotted as arrows on the particle plot using the "arrow" function,
    % and the plot is updated with each iteration. 
    start = xy;
    stop = start + Fbalance./distance(Fbalance).*flog*flogscale;
    start(flog<flogmin,:) = [];
    stop(flog<flogmin,:) = [];
    if ~isempty(hp), delete(hp{1}), delete(hp{2}), delete(hp{3}), end
    if ~isempty(ha), delete(ha); end
    hp = {layerplot(config1); layerplot(config2); layerplot(config3)};
    ha = [
        arrow(start,stop,'length',4,'BaseAngle',60,'Linewidth',1,'color',rgb('ForestGreen'),'Edgecolor',rgb('ForestGreen'))
        %arrow(start,[stop(:,1) start(:,2)],'length',4,'BaseAngle',60,'color',rgb('Tomato'))
        %arrow(start,[start(:,1) stop(:,2)],'length',4,'BaseAngle',60,'color',rgb('Tomato'),'EdgeColor',rgb('Tomato'))
    ];
    axis(ax)
    drawnow

   %If the "RECORD" flag is set to true, the plot is also recorded as a GIF using the "gif_add_frame" function.
   if RECORD
       gif_add_frame(gca,'landshoff_obstacle.gif',15);
   end

end