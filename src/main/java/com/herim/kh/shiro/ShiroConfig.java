package com.herim.kh.shiro;

import java.util.LinkedHashMap;
import java.util.Map;

import org.apache.shiro.authc.credential.HashedCredentialsMatcher;
import org.apache.shiro.mgt.SecurityManager;
import org.apache.shiro.spring.security.interceptor.AuthorizationAttributeSourceAdvisor;
import org.apache.shiro.spring.web.ShiroFilterFactoryBean;
import org.apache.shiro.web.mgt.DefaultWebSecurityManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ShiroConfig {
	
	/**
	 * 采用MD5加密
	 * @return
	 */
	@Bean
	public HashedCredentialsMatcher hashedCredentialsMatcher() {
		HashedCredentialsMatcher hcm = new HashedCredentialsMatcher();
		// 散列算法:这里使用MD5算法;
		hcm.setHashAlgorithmName("MD5");
		//散列的次数，比如散列两次，相当于 md5(md5(""));
		hcm.setHashIterations(2);
		//storedCredentialsHexEncoded默认是true，此时用的是密码加密用的是Hex编码；false时用Base64编码
		hcm.setStoredCredentialsHexEncoded(true);
		return hcm;
		
	}

	@Bean
	public ShiroFilterFactoryBean shiroFilterFactoryBean(SecurityManager securityManager) {
		ShiroFilterFactoryBean shiroFilterFactoryBean = new ShiroFilterFactoryBean();
		shiroFilterFactoryBean.setSecurityManager(securityManager);
		//拦截器.
		Map<String, String> filterChainDefinitionMap = new LinkedHashMap<String, String>();
        // 配置不会被拦截的链接 顺序判断
        filterChainDefinitionMap.put("/static/**", "anon");
        filterChainDefinitionMap.put("/h2-console/**", "anon");
        filterChainDefinitionMap.put("/user/to-register", "anon");
        filterChainDefinitionMap.put("/user/register", "anon");
        filterChainDefinitionMap.put("/user/generate/all", "anon");
        filterChainDefinitionMap.put("/dept/add", "anon");
        //配置退出 过滤器,其中的具体的退出代码Shiro已经替我们实现了
        filterChainDefinitionMap.put("/user/logout", "logout");
        filterChainDefinitionMap.put("/user/login", "anon");
        filterChainDefinitionMap.put("/admin/to-score/**", "anon");
        filterChainDefinitionMap.put("/operation/**", "anon");
        filterChainDefinitionMap.put("/myconfig/**", "anon");
        filterChainDefinitionMap.put("/admin/export-score/**", "anon");
        //<!-- 过滤链定义，从上向下顺序执行，一般将/**放在最为下边 -->:这是一个坑呢，一不小心代码就不好使了;
        //<!-- authc:所有url都必须认证通过才可以访问; anon:所有url都都可以匿名访问-->
        filterChainDefinitionMap.put("/**", "authc");
        // 如果不设置默认会自动寻找Web工程根目录下的"/login.jsp"页面
        shiroFilterFactoryBean.setLoginUrl("/user/to-login");
        // 登录成功后要跳转的链接
        shiroFilterFactoryBean.setSuccessUrl("/user/to-assess");
        //filterChainDefinitionMap.put(“/add”, “roles[100002]，perms[权限添加]”);
        //未授权界面;
        shiroFilterFactoryBean.setUnauthorizedUrl("/403");
		shiroFilterFactoryBean.setFilterChainDefinitionMap(filterChainDefinitionMap);
		return shiroFilterFactoryBean;
	}

	@Bean
	public DefaultWebSecurityManager securityManager() {
		DefaultWebSecurityManager defaultWebSecurityManager = new DefaultWebSecurityManager();
		defaultWebSecurityManager.setRealm(myRealm());
		return defaultWebSecurityManager;
	}

	@Bean
	public MyRealm myRealm() {
		MyRealm myRealm = new MyRealm();
		myRealm.setCredentialsMatcher(hashedCredentialsMatcher());
		return myRealm;
	}
	
	 //加入注解的使用，不加入这个注解不生效
    @Bean
    public AuthorizationAttributeSourceAdvisor authorizationAttributeSourceAdvisor(SecurityManager securityManager) {
        AuthorizationAttributeSourceAdvisor authorizationAttributeSourceAdvisor = new AuthorizationAttributeSourceAdvisor();
        authorizationAttributeSourceAdvisor.setSecurityManager(securityManager);
        return authorizationAttributeSourceAdvisor;
    }
}
