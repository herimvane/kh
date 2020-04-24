package com.herim.kh.shiro;

import java.util.List;

import org.apache.shiro.SecurityUtils;
import org.apache.shiro.authc.AuthenticationException;
import org.apache.shiro.authc.AuthenticationInfo;
import org.apache.shiro.authc.AuthenticationToken;
import org.apache.shiro.authc.SimpleAuthenticationInfo;
import org.apache.shiro.authc.UnknownAccountException;
import org.apache.shiro.authz.AuthorizationInfo;
import org.apache.shiro.authz.SimpleAuthorizationInfo;
import org.apache.shiro.realm.AuthorizingRealm;
import org.apache.shiro.subject.PrincipalCollection;
import org.apache.shiro.util.ByteSource;
import org.springframework.beans.factory.annotation.Autowired;

import com.herim.kh.domain.Permission;
import com.herim.kh.domain.Role;
import com.herim.kh.domain.User;
import com.herim.kh.service.UserService;

public class MyRealm extends AuthorizingRealm{
	
	@Autowired
	private UserService userService;

	/**
	 * 授权
	 */
	@Override
	protected AuthorizationInfo doGetAuthorizationInfo(PrincipalCollection principals) {
		 //从凭证中获得用户名
        String username = (String) SecurityUtils.getSubject().getPrincipal();
        //根据用户名查询用户对象
        User user = userService.findByName(username);
        //查询用户拥有的角色
        List<Role> roles = user.getRoles();
        SimpleAuthorizationInfo info = new SimpleAuthorizationInfo();
        for (Role role : roles) {
        	for(Permission permission : role.getPermissions()) {
        		info.addStringPermission(permission.getName());
        	}
        }
        for(Permission permission : user.getPermissions()) {
        	info.addStringPermission(permission.getName());
        }
        return info;
	}

	/**
	 * 认证
	 */
	@Override
	protected AuthenticationInfo doGetAuthenticationInfo(AuthenticationToken token) throws AuthenticationException {
		
		
        //获得当前用户的用户名
        String username = (String) token.getPrincipal();
        //从数据库中根据用户名查找用户
        User user = userService.findByName(username);
        if (user == null) {
            throw new UnknownAccountException(
                    "未知账户	");
        }
       SimpleAuthenticationInfo info = new SimpleAuthenticationInfo(user.getName(), user.getPassword(),ByteSource.Util.bytes(user.getName()), this.getName());
        //SimpleAuthenticationInfo info = new SimpleAuthenticationInfo(user.getName(), user.getPassword(),ByteSource.Util.bytes("文仙运"), this.getName());
        return info;
	}

	
}
